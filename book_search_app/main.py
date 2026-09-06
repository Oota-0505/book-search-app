"""Book Finder — FastAPI アプリケーション本体。

画面は1ページだけ。最初のHTMLは即座に返し、検索は
/api/search を fetch して非同期に描画する。
（画面表示のために外部サイトの応答を待たない）
"""

from __future__ import annotations

import logging
import mimetypes
import os

from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import history, logging_config, providers, search
from .config import (
    APP_DESCRIPTION,
    APP_NAME,
    APP_SHORT_NAME,
    HISTORY_LIMIT,
    MAX_KEYWORD_LENGTH,
    STATIC_DIR,
    TEMPLATES_DIR,
    THEME_COLOR,
    asset_version,
)

from fastapi import Body
from . import push
from .config import VAPID_PUBLIC_KEY



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


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """入力エラーもフロントが読む {"error": ...} の形で返す。"""
    logger.info("入力エラー: %s %s", request.url.path, exc.errors())
    return JSONResponse(
        {"error": f"キーワードは{MAX_KEYWORD_LENGTH}文字以内で入力してください"},
        status_code=400,
    )


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
            "history": history.load(),
            "history_limit": HISTORY_LIMIT,
            "asset_version": _asset_version(),
        },
    )


# ============================================================================
# API
# ============================================================================

@app.get("/api/search", include_in_schema=False)
def api_search(q: str = Query(default="", max_length=MAX_KEYWORD_LENGTH)) -> JSONResponse:
    """4サイトを並列に検索して結果を返す。

    同期関数として定義しているので、FastAPI がスレッドプールで実行する。
    （外部サイトの応答待ちでイベントループを止めない）
    """
    keyword = q.strip()
    if not keyword:
        return JSONResponse({"error": "キーワードを入力してください"}, status_code=400)

    results, from_cache = search.search(keyword)
    return JSONResponse(
        {
            "keyword": keyword,
            "cached": from_cache,
            "amazon_url": providers.build_amazon_url(keyword),
            "results": [r.to_dict() for r in results],
            "history": history.add(keyword),
        }
    )


@app.get("/api/history", include_in_schema=False)
async def api_history_get() -> JSONResponse:
    return JSONResponse({"history": history.load()})



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
