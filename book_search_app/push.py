"""Web Push の購読管理と送信。

Laravel では laravel-notification-channels/webpush が
`push_subscriptions` テーブルと HasPushSubscriptions trait で
同じ役割を担う。
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List

from pywebpush import WebPushException, webpush

from .config import (
    DATA_DIR,
    SUBSCRIPTIONS_FILE,
    VAPID_PRIVATE_KEY_PATH,
    VAPID_SUBJECT,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _load() -> List[Dict[str, Any]]:
    try:
        with SUBSCRIPTIONS_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("購読情報の読み込みに失敗: %s", exc)
        return []


def _save(subscriptions: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SUBSCRIPTIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(subscriptions, f, ensure_ascii=False, indent=2)


def add(subscription: Dict[str, Any]) -> None:
    """購読を登録する（同じ endpoint は上書き）。"""
    with _lock:
        subscriptions = [s for s in _load() if s.get("endpoint") != subscription.get("endpoint")]
        subscriptions.append(subscription)
        _save(subscriptions)
        logger.info("購読を登録しました（現在 %d 件）", len(subscriptions))


def remove(endpoint: str) -> None:
    with _lock:
        subscriptions = [s for s in _load() if s.get("endpoint") != endpoint]
        _save(subscriptions)


def count() -> int:
    """保存されている購読の件数（診断用）。"""
    return len(_load())


def send(title: str, body: str, url: str = "/", badge_count: int | None = None) -> Dict[str, int]:
    """登録済みの全端末へ通知を送る。

    ⚠️ iOS は showNotification を伴わない push を「サイレント」とみなし、
       数回続くと購読を解除する。payload には必ず表示内容を入れること。
    """
    payload = json.dumps(
        {"title": title, "body": body, "url": url, "count": badge_count},
        ensure_ascii=False,
    )

    sent = 0
    expired: List[str] = []

    for subscription in _load():
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=str(VAPID_PRIVATE_KEY_PATH),
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                # 端末側で購読が失効している。掃除する
                expired.append(subscription["endpoint"])
                logger.info("失効した購読を削除します: %s", status)
            else:
                logger.error("プッシュ送信に失敗: %s", exc)

    for endpoint in expired:
        remove(endpoint)

    return {"sent": sent, "expired": len(expired)}