"""受取待ちの本のリスト。

図書館から「予約本が用意できました」のメールが来たら、Apps Script が
/api/notify を叩き、ここに保存される。通知は消えてしまうので、
アプリを開けば「どの本を・いつまでに」取りに行けばよいか分かるようにする。
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .config import DATA_DIR, PENDING_FILE

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# 岐阜市の取り置き期間。「連絡日の翌日から7開館日」だが、休館日は
# メールから分からない。休館日ゼロと仮定した「一番早い期限」を使う。
# 実際の期限がこれより早まることはないので、この日までに行けば必ず間に合う。
GIFU_PICKUP_DAYS = 7

# 期限を過ぎてもすぐには消さない（受け取り済みの押し忘れに備える）
KEEP_DAYS_AFTER_DUE = 3

LIBRARY_NAMES = {"gifu": "メディコス", "kani": "カニミライブ図書館"}


@dataclass
class PendingBook:
    """受取待ちの1冊。"""

    id: str
    library: str          # "gifu" | "kani"
    title: str
    branch: Optional[str]  # 受取館（岐阜市のみメールに入っている）
    due: str              # 受取期限 YYYY-MM-DD
    due_is_estimate: bool  # 岐阜市は「7開館日」からの推定なので True
    received: str         # 連絡日 YYYY-MM-DD

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["library_name"] = LIBRARY_NAMES.get(self.library, self.library)
        data["days_left"] = (date.fromisoformat(self.due) - date.today()).days
        data["where"] = self.branch or data["library_name"]
        return data


def deadline_for(library: str, received: date, stated_due: Optional[str]) -> tuple[str, bool]:
    """受取期限と、それが推定かどうかを返す。

    可児市はメール本文に日付があるのでそれを使う（推定ではない）。
    岐阜市は「連絡日の翌日から7開館日」としか書かれておらず、休館日を
    数えないと正確な日付が出せない。休館日カレンダーは取りに行かない方針なので、
    休館日ゼロと仮定した一番早い期限を返す（安全側に倒す）。
    """
    if stated_due:
        try:
            return date.fromisoformat(stated_due.replace("/", "-")).isoformat(), False
        except ValueError:
            logger.warning("期限の形式が読めません: %r", stated_due)
    return (received + timedelta(days=GIFU_PICKUP_DAYS)).isoformat(), True


def _load() -> List[Dict[str, Any]]:
    try:
        with PENDING_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("受取待ちリストの読み込みに失敗: %s", exc)
        return []


def _save(books: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with PENDING_FILE.open("w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)


def _drop_expired(books: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """期限を過ぎて一定日数たったものを落とす。"""
    limit = date.today() - timedelta(days=KEEP_DAYS_AFTER_DUE)
    kept = []
    for book in books:
        try:
            if date.fromisoformat(book["due"]) >= limit:
                kept.append(book)
        except (KeyError, ValueError):
            kept.append(book)   # 壊れたデータは消さずに残す（原因を追えるように）
    return kept


def add_many(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apps Script から届いた本を登録し、更新後のリストを返す。

    同じ図書館・同じ書名は重複させない（同じメールを二度拾った場合に備える）。
    """
    with _lock:
        books = _drop_expired(_load())
        known = {(b.get("library"), b.get("title")) for b in books}

        for entry in entries:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            library = entry.get("library") or "gifu"
            if (library, title) in known:
                continue

            try:
                received = date.fromisoformat(entry["received"])
            except (KeyError, ValueError):
                received = date.today()

            due, is_estimate = deadline_for(library, received, entry.get("due"))
            books.append(asdict(PendingBook(
                id=uuid.uuid4().hex[:12],
                library=library,
                title=title,
                branch=(entry.get("branch") or None),
                due=due,
                due_is_estimate=is_estimate,
                received=received.isoformat(),
            )))
            known.add((library, title))

        books.sort(key=lambda b: b.get("due", ""))
        _save(books)
        logger.info("受取待ちに追加しました（現在 %d 冊）", len(books))
        return books


def load() -> List[Dict[str, Any]]:
    """期限切れを掃除したうえで、期限の近い順に返す。"""
    with _lock:
        books = _drop_expired(_load())
        books.sort(key=lambda b: b.get("due", ""))
        _save(books)
    return [PendingBook(**{k: v for k, v in b.items() if k in PendingBook.__annotations__}).to_dict()
            for b in books]


def remove(book_id: str) -> bool:
    """「受け取った」で1冊消す。消せたら True。"""
    with _lock:
        books = _load()
        kept = [b for b in books if b.get("id") != book_id]
        if len(kept) == len(books):
            return False
        _save(kept)
        logger.info("受取済みにしました: %s", book_id)
        return True
