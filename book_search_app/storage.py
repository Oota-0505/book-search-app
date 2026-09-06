"""小さなキー・バリュー保存。

手元ではファイル、Cloudflare Workers では KV に保存する。
Workers にはファイルシステムが無く、Cloud Run もコンテナが消えると
ファイルが消えるため、保存先を差し替えられるようにしておく。

使う側（push.py / pending.py）は get / set しか知らない。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional, Protocol

from .config import DATA_DIR

logger = logging.getLogger(__name__)


class Store(Protocol):
    """保存先の共通の形。"""

    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...


class FileStore:
    """1キー1ファイルで JSON を保存する（手元での実行用）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _path(self, key: str):
        # キーはコード内の定数だけなので、素直にファイル名にする
        return DATA_DIR / f"{key}.json"

    def get(self, key: str) -> Optional[Any]:
        try:
            with self._path(key).open(encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("%s の読み込みに失敗: %s", key, exc)
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = self._path(key)
            # 書き込み中に落ちても壊れないよう、別名で書いてから差し替える
            tmp = path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
            tmp.replace(path)


class MemoryStore:
    """テスト用。プロセス内だけに持つ。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


class KVStore:
    """Cloudflare Workers の KV に保存する。

    Workers 上では JS の KV バインディングが env 経由で渡ってくる。
    ここはデプロイ時に配線する想定で、それまでは使われない。
    """

    def __init__(self, binding: Any) -> None:
        self._kv = binding

    def get(self, key: str) -> Optional[Any]:
        raw = self._kv.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any) -> None:
        self._kv.put(key, json.dumps(value, ensure_ascii=False))


_store: Store = MemoryStore() if os.environ.get("BOOKFINDER_MEMORY_STORE") else FileStore()


def get_store() -> Store:
    return _store


def use(store: Store) -> None:
    """保存先を差し替える（テストと、Workers での配線用）。"""
    global _store
    _store = store
