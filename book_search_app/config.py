"""アプリ全体で使う定数と設定。

パスはすべてこのファイルの位置を基準に解決する。
（カレントディレクトリに依存すると、起動場所によって
  ログや履歴の保存先がずれるため）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Final

# ── ディレクトリ ────────────────────────────────────────────────
APP_DIR: Final[Path] = Path(__file__).resolve().parent
STATIC_DIR: Final[Path] = APP_DIR / "static"
TEMPLATES_DIR: Final[Path] = APP_DIR / "templates"
DATA_DIR: Final[Path] = APP_DIR / "data"
LOG_DIR: Final[Path] = APP_DIR.parent / "logs"

# ── HTTP リクエスト設定 ─────────────────────────────────────────
# アプリ識別子を付けて、アクセス元を各サイトから判別できるようにしている
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "BookFinder/1.0 (personal-use)"
)
HEADERS: Final[Dict[str, str]] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
TIMEOUT_SHORT: Final[int] = 10
TIMEOUT_MEDIUM: Final[int] = 20

# ── アプリ設定 ──────────────────────────────────────────────────
KUSA_BOOKS_KEYWORD: Final[str] = "各務原店"

# 同一キーワードの再検索で各サイトへ再アクセスしない猶予時間（サーバー負荷軽減）
CACHE_TTL_SECONDS: Final[int] = 600

# 検索キーワードの上限。長すぎる文字列を相手サイトへ投げないための保険
MAX_KEYWORD_LENGTH: Final[int] = 120

# ── PWA ────────────────────────────────────────────────────────
APP_NAME: Final[str] = "Book Finder"
APP_SHORT_NAME: Final[str] = "BookFinder"
APP_DESCRIPTION: Final[str] = "岐阜の図書館・書店の在庫をまとめて検索できるアプリ"
THEME_COLOR: Final[str] = "#0C0820"


def asset_version() -> str:
    """CSS/JS のキャッシュバスター用の短いハッシュ。

    Service Worker は /static/ を cache-first で持つため、URL が変わらないと
    編集しても古いファイルが表示され続ける。ファイルの更新時刻から
    版を作り、`app.css?v=...` の形で付けることでこれを避ける。
    """
    import hashlib

    watched = sorted(STATIC_DIR.glob("css/*.css")) + sorted(STATIC_DIR.glob("js/*.js"))
    digest = hashlib.sha256()
    for path in watched:
        digest.update(f"{path.name}:{path.stat().st_mtime_ns}".encode())
    return digest.hexdigest()[:10]




# ── Web Push ───────────────────────────────────────────────────
# A-2 で表示された公開鍵を貼る
VAPID_PUBLIC_KEY: Final[str] = "BKETLN4gWm88gzdLc45lXhgvbVTGfsyBGfDf5PWYcx5EfHn7w3DpX13v1US7_-hk_bi5q2xWQVieQ9O2FimMqts"
VAPID_PRIVATE_KEY_PATH: Final[Path] = DATA_DIR / "vapid_private.pem"

# ⚠️ Apple は mailto: か HTTPS URL 以外だと 403 を返す（Laravel の VAPID_SUBJECT と同じ）
VAPID_SUBJECT: Final[str] = "mailto:sin5531@gmail.com"

# ── 受取待ちリスト（Phase E）────────────────────────────────────
_NOTIFY_TOKEN_FILE: Final[Path] = DATA_DIR / "notify_token.txt"


def notify_token() -> str:
    """Apps Script からの通知を受け取るときの合言葉。

    環境変数 BOOKFINDER_NOTIFY_TOKEN があればそれを使う（本番向け）。
    無ければ data/ に生成して使い回す（手元ですぐ動かせるように）。
    """
    import os
    import secrets

    from_env = os.environ.get("BOOKFINDER_NOTIFY_TOKEN")
    if from_env:
        return from_env

    if _NOTIFY_TOKEN_FILE.exists():
        return _NOTIFY_TOKEN_FILE.read_text(encoding="utf-8").strip()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    _NOTIFY_TOKEN_FILE.write_text(token, encoding="utf-8")
    _NOTIFY_TOKEN_FILE.chmod(0o600)
    return token