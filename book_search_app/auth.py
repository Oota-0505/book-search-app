"""単一ユーザー向けの簡易ログイン。

公開ホスティングに置くと URL を知っている人は誰でも開けてしまう。
検索履歴や受取待ちの本（＝読んでいる本）が見えるうえ、図書館・書店への
アクセスを他人に肩代わりすることにもなるため、認証で自分専用に保つ。

PWA ではブラウザの Basic 認証ダイアログが扱いにくいので、
パスワード1つ + 署名付き Cookie の形にしている。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from typing import Awaitable, Callable

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.requests import Request
from starlette.responses import Response

from .config import DATA_DIR

logger = logging.getLogger(__name__)

COOKIE_NAME = "bf_session"
MAX_AGE = 60 * 60 * 24 * 365  # 1年。毎回ログインさせたいものではない

_SECRET_FILE = DATA_DIR / "session_secret.txt"

# 認証なしで通すパス。
# ⚠️ ここを塞ぐと PWA としてインストールできなくなる（manifest と sw.js が
#    読めないため）。いずれも中身は非機密なので公開して問題ない。
PUBLIC_PATHS = frozenset({
    "/login",
    "/logout",
    "/sw.js",
    "/manifest.webmanifest",
    "/offline.html",
    "/favicon.ico",
    "/robots.txt",
    # Apps Script は Cookie を持たない。ここは自前の Bearer トークンで守る
    "/api/notify",
})
PUBLIC_PREFIXES = ("/static/",)


def password() -> str:
    """設定されているパスワード。空ならログイン不要（手元での開発用）。"""
    return os.environ.get("BOOKFINDER_PASSWORD", "")


def _secret() -> bytes:
    """Cookie の署名鍵。無ければ生成して使い回す。

    鍵が変わると全端末のログインが切れるので、ファイルに保存しておく。
    """
    from_env = os.environ.get("BOOKFINDER_SECRET")
    if from_env:
        return from_env.encode()

    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes().strip()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32).encode()
    _SECRET_FILE.write_bytes(value)
    _SECRET_FILE.chmod(0o600)
    return value


def _sign(issued_at: str) -> str:
    return hmac.new(_secret(), issued_at.encode(), hashlib.sha256).hexdigest()


def make_cookie_value() -> str:
    issued_at = str(int(time.time()))
    return f"{issued_at}.{_sign(issued_at)}"


def is_valid(cookie: str | None) -> bool:
    if not cookie or "." not in cookie:
        return False
    issued_at, signature = cookie.rsplit(".", 1)
    # compare_digest を使う（== はタイミング攻撃に弱い）
    if not hmac.compare_digest(_sign(issued_at), signature):
        return False
    try:
        return time.time() - int(issued_at) < MAX_AGE
    except ValueError:
        return False


# ── 総当たり対策 ────────────────────────────────────────────────
# 公開すると URL は証明書の透明性ログから見つかりうるので、
# ログイン画面に無制限の試行をさせない。
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def _recent_failures(client: str) -> int:
    now = time.time()
    with _attempts_lock:
        stamps = [t for t in _attempts.get(client, []) if now - t < LOCKOUT_SECONDS]
        _attempts[client] = stamps
        return len(stamps)


def record_failure(client: str) -> None:
    with _attempts_lock:
        _attempts.setdefault(client, []).append(time.time())


def clear_failures(client: str) -> None:
    with _attempts_lock:
        _attempts.pop(client, None)


def is_locked_out(client: str) -> bool:
    return _recent_failures(client) >= MAX_ATTEMPTS


def check_password(given: str) -> bool:
    expected = password()
    return bool(expected) and hmac.compare_digest(given, expected)


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


async def require_login(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """未ログインならログイン画面へ送るミドルウェア。"""
    if not password() or is_public(request.url.path):
        return await call_next(request)

    if is_valid(request.cookies.get(COOKIE_NAME)):
        return await call_next(request)

    # API は画面遷移させず、フロントが扱える形で返す
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "ログインが必要です"}, status_code=401)

    return RedirectResponse("/login", status_code=303)
