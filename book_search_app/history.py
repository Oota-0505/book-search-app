"""検索履歴の永続化（JSONファイル）。

アプリを再起動しても直近の検索を復元できるようにする。
検索キーワードは個人情報になりうるため、保存先は .gitignore 済み。
"""

from __future__ import annotations

import json
import logging
import threading
from typing import List

from .config import HISTORY_FILE, HISTORY_LIMIT, DATA_DIR

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def load() -> List[str]:
    """履歴を読み込む（ファイルが無い・壊れている場合は空リスト）。"""
    try:
        with HISTORY_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("検索履歴の読み込みに失敗: %s", exc)
        return []

    if not isinstance(data, list):
        logger.warning("検索履歴の形式が不正なため無視する: %s", HISTORY_FILE)
        return []
    return [str(kw) for kw in data][:HISTORY_LIMIT]


def _save(history: List[str]) -> None:
    """履歴を書き込む。書き込み失敗はアプリを止めない（履歴は補助機能のため）。"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("検索履歴の保存に失敗: %s", exc)


def add(keyword: str) -> List[str]:
    """キーワードを先頭に追加して保存し、更新後の履歴を返す。"""
    keyword = keyword.strip()
    if not keyword:
        return load()

    with _lock:
        history = load()
        if keyword in history:
            history.remove(keyword)
        history.insert(0, keyword)
        history = history[:HISTORY_LIMIT]
        _save(history)
        return history

