#!/usr/bin/env python3
"""Book Finder の起動スクリプト。

    python run.py                      # http://127.0.0.1:8000
    python run.py --reload             # ファイルを保存すると自動再起動（開発用）
    python run.py --host 0.0.0.0       # 同じWi-Fi内のスマホから開く

スマホでPWAとして使う（オフライン対応・ホーム画面から全画面起動）には
HTTPS が必要です。LAN内の http://192.168.x.x では Service Worker が動きません。
Tailscale なら無料で HTTPS を用意できます:

    tailscale serve --bg 8000
"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Book Finder を起動する")
    parser.add_argument("--host", default="127.0.0.1", help="待ち受けアドレス")
    parser.add_argument("--port", type=int, default=8000, help="待ち受けポート")
    parser.add_argument("--reload", action="store_true", help="自動再起動（開発用）")
    args = parser.parse_args()

    if args.reload:
        # CSS/JS を編集したら再起動なしで反映させる（main.py が参照する）
        os.environ["BOOKFINDER_DEV"] = "1"

    uvicorn.run(
        "book_search_app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        # アクセスログはアプリ側のロガーと二重になるので出さない
        access_log=False,
    )


if __name__ == "__main__":
    main()
