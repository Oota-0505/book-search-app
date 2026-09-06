"""Book Finder — FastAPI アプリケーション本体。

画面は1ページだけ。最初のHTMLは即座に返し、検索は
/api/search を fetch して非同期に描画する。
（画面表示のために外部サイトの応答を待たない）
"""

from __future__ import annotations

import logging
import mimetypes
import os
import secrets
from datetime import date

from fastapi import Body, FastAPI, Form, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import auth, logging_config, pending, providers, push, search
from .config import (
    APP_DESCRIPTION,
    APP_NAME,
    APP_SHORT_NAME,
    MAX_KEYWORD_LENGTH,
    STATIC_DIR,
    TEMPLATES_DIR,
    THEME_COLOR,
    VAPID_PUBLIC_KEY,
    asset_version,
    notify_token,
)


# .webmanifest は環境によって未知の拡張子扱いになるため明示する
mimetypes.add_type("application/manifest+json", ".webmanifest")

logging_config.setup()
logger = logging.getLogger(__name__)

# 本番は起動時に1度だけ算出する（リクエストごとに stat しない）。
# 開発中（run.py --reload）は毎回計算し、CSS/JS を編集したら
# サーバーを再起動しなくても反映されるようにする。
_DEV = os.environ.get("BOOKFINDER_DEV") == "1"
ASSET_VERSION = asset_version()


def _asset_version() -> str:
    return asset_version() if _DEV else ASSET_VERSION

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 未ログインを弾く。PWA に必要なファイルと /api/notify は通す（auth.py 参照）
app.middleware("http")(auth.require_login)


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """入力エラーもフロントが読む {"error": ...} の形で返す。"""
    logger.info("入力エラー: %s %s", request.url.path, exc.errors())
    return JSONResponse(
        {"error": f"キーワードは{MAX_KEYWORD_LENGTH}文字以内で入力してください"},
        status_code=400,
    )


# ============================================================================
# ログイン
# ============================================================================

@app.get("/login", include_in_schema=False)
async def login_form(request: Request, error: int = 0) -> object:
    if not auth.password() or auth.is_valid(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html",
        {"app_name": APP_NAME, "theme_color": THEME_COLOR, "error": error},
    )


@app.post("/login", include_in_schema=False)
async def login(request: Request, password: str = Form(...)) -> RedirectResponse:
    client = request.client.host if request.client else "unknown"

    if auth.is_locked_out(client):
        logger.warning("試行回数の上限に達しています: %s", client)
        return RedirectResponse("/login?error=2", status_code=303)

    if not auth.check_password(password):
        auth.record_failure(client)
        logger.warning("ログインに失敗しました: %s", client)
        return RedirectResponse("/login?error=1", status_code=303)

    auth.clear_failures(client)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.make_cookie_value(),
        max_age=auth.MAX_AGE,
        httponly=True,
        samesite="lax",
        # 手元の http://127.0.0.1 でも動くよう、HTTPS のときだけ secure にする
        secure=bool(os.environ.get("BOOKFINDER_SECURE_COOKIE", "1") == "1"),
    )
    return response


@app.get("/logout", include_in_schema=False)
async def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME)
    return response


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> PlainTextResponse:
    """個人用アプリなので検索エンジンには載せない。"""
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


# ============================================================================
# 画面
# ============================================================================

@app.get("/", include_in_schema=False)
async def index(request: Request) -> object:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": APP_NAME,
            "app_short_name": APP_SHORT_NAME,
            "description": APP_DESCRIPTION,
            "theme_color": THEME_COLOR,
            "asset_version": _asset_version(),
        },
    )


# ============================================================================
# API
# ============================================================================

@app.get("/api/search", include_in_schema=False)
async def api_search(q: str = Query(default="", max_length=MAX_KEYWORD_LENGTH)) -> JSONResponse:
    """4サイトを並行に検索して結果を返す。

    通信待ちの間はイベントループを手放すので、非同期のまま扱える。
    """
    keyword = q.strip()
    if not keyword:
        return JSONResponse({"error": "キーワードを入力してください"}, status_code=400)

    results, from_cache = await search.search(keyword)
    return JSONResponse(
        {
            "keyword": keyword,
            "cached": from_cache,
            "amazon_url": providers.build_amazon_url(keyword),
            "results": [r.to_dict() for r in results],
        }
    )



# ============================================================================
# PWA（ルート直下で配る必要があるファイル）
# ============================================================================

@app.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    """Service Worker。

    ルートスコープを取るために /static ではなく / で配る。
    Cache-Control: no-cache を付けないと、古いSWが端末に残り続ける。
    """
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/offline.html", include_in_schema=False)
async def offline() -> FileResponse:
    return FileResponse(STATIC_DIR / "offline.html", media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "icons/icon-192.png", media_type="image/png")


@app.get("/api/push/key", include_in_schema=False)
async def push_key() -> JSONResponse:
    """ブラウザが購読するときに使う公開鍵を返す。"""
    return JSONResponse({"key": VAPID_PUBLIC_KEY})


@app.post("/api/push/subscribe", include_in_schema=False)
async def push_subscribe(subscription: dict = Body(...)) -> JSONResponse:
    if not subscription.get("endpoint"):
        return JSONResponse({"error": "購読情報が不正です"}, status_code=400)
    push.add(subscription)
    return JSONResponse({"ok": True})


@app.get("/api/push/status", include_in_schema=False)
async def push_status() -> JSONResponse:
    """診断用。サーバーに保存されている購読の件数を返す。"""
    return JSONResponse({"count": push.count()})


@app.post("/api/push/test", include_in_schema=False)
def push_test() -> JSONResponse:
    """動作確認用。Phase E で Gmail 連携に置き換える。"""
    result = push.send(
        title="📚 予約本が届きました",
        body="メディコスで1冊、受け取り待ちです",
        url="/?from=push",
        badge_count=1,
    )
    return JSONResponse(result)


# ============================================================================
# 受取待ちリスト（図書館からの予約本お取り置きメール）
# ============================================================================

@app.get("/api/pending", include_in_schema=False)
async def api_pending() -> JSONResponse:
    """受取待ちの本を、期限の近い順に返す。"""
    return JSONResponse({"books": pending.load()})


@app.delete("/api/pending/{book_id}", include_in_schema=False)
async def api_pending_delete(book_id: str) -> JSONResponse:
    """「受け取った」で1冊消す。"""
    if not pending.remove(book_id):
        return JSONResponse({"error": "見つかりません"}, status_code=404)
    return JSONResponse({"books": pending.load()})


@app.post("/api/notify", include_in_schema=False)
def api_notify(
    payload: dict = Body(...),
    authorization: str = Header(default=""),
) -> JSONResponse:
    """Apps Script から呼ばれ、予約本の到着を登録して通知する。

    同期関数にしているのは、プッシュ送信が通信待ちでブロックするため
    （FastAPI がスレッドプールで実行してくれる）。
    """
    expected = f"Bearer {notify_token()}"
    if not secrets.compare_digest(authorization, expected):
        logger.warning("/api/notify に不正なトークンでアクセスがありました")
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    entries = payload.get("books") or []
    if not entries:
        return JSONResponse({"error": "books が空です"}, status_code=400)

    before = {b["id"] for b in pending.load()}
    books = pending.add_many(entries)
    added = [b for b in pending.load() if b["id"] not in before]

    if not added:
        # 同じメールを二度拾っただけ。通知は送らない
        logger.info("新規の予約本はありませんでした")
        return JSONResponse({"added": 0, "sent": 0, "total": len(books)})

    first = added[0]
    body = f"{first['title']}（{first['where']}）・{_format_due(first['due'])}まで"
    if len(added) > 1:
        body += f" ほか{len(added) - 1}冊"

    result = push.send(
        title="📚 予約本が届きました",
        body=body,
        url=f"/?from=push&lib={first['library']}",
        badge_count=len(pending.load()),
    )
    return JSONResponse({"added": len(added), "total": len(books), **result})


def _format_due(iso_date: str) -> str:
    """2026-09-13 → 9/13"""
    try:
        d = date.fromisoformat(iso_date)
        return f"{d.month}/{d.day}"
    except ValueError:
        return iso_date
