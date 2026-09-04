"""アプリ共通のロギング設定。"""

from __future__ import annotations

import logging
import logging.handlers

from .config import LOG_DIR

_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s.%(funcName)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup(level: int = logging.INFO) -> None:
    """ファイル（日次ローテート）とコンソールの両方へ出力する。

    多重呼び出しでハンドラが増えないよう、設定済みなら何もしない。
    """
    root = logging.getLogger("book_search_app")
    if root.handlers:
        return

    root.setLevel(level)
    root.propagate = False
    formatter = logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FORMAT)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "app.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
