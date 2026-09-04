"""在庫ステータスと検索結果のデータモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Final


@dataclass(frozen=True)
class BookStatus:
    """各サイトの在庫状況を表す不変データ。

    tone は表示色の種類（ok / ng / warn / link）で、
    CSS のクラス名にそのまま対応する。
    """

    text: str
    tone: str
    icon: str

    def to_dict(self) -> Dict[str, str]:
        return {"text": self.text, "tone": self.tone, "icon": self.icon}


# ── ステータス定数 ──────────────────────────────────────────────
AVAILABLE: Final[BookStatus] = BookStatus("在庫あり", "ok", "⭕️")
NONE_FOUND: Final[BookStatus] = BookStatus("なし", "ng", "❌")
PENDING: Final[BookStatus] = BookStatus("判定保留", "warn", "⚠️")
ERROR: Final[BookStatus] = BookStatus("エラー", "warn", "⚠️")
LINK_ONLY: Final[BookStatus] = BookStatus("リンクで確認", "link", "🔗")


def hit_count(total: int) -> BookStatus:
    """件数はわかったが在庫の内訳が不明なときのステータス。"""
    return BookStatus(f"{total}件", "warn", "⚠️")


@dataclass(frozen=True)
class SiteResult:
    """1サイト分の検索結果。そのままJSONにしてフロントへ渡す。"""

    key: str
    name: str
    icon: str
    status: BookStatus
    url: str
    image: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "icon": self.icon,
            "status": self.status.to_dict(),
            "url": self.url,
            "image": self.image,
        }
