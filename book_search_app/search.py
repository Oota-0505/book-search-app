"""4サイトの並列検索と、結果のTTLキャッシュ。"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

from . import models, providers
from .config import CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

CheckFn = Callable[[httpx.AsyncClient, str], Awaitable[Tuple[models.BookStatus, str]]]
LinkFn = Callable[[str], str]


@dataclass(frozen=True)
class Site:
    """検索対象サイトの定義。表示順はこのタプルの並び順。

    check が想定外の例外で落ちてもカードのリンクだけは生かせるよう、
    link（リクエストを送らないURLビルダー）を必ず持たせている。
    """

    key: str
    name: str
    icon: str
    image: str
    check: CheckFn
    link: LinkFn


SITES: Tuple[Site, ...] = (
    Site("gifu", "メディコス", "🏢", "/static/images/medicos.webp",
         providers.check_gifu, providers.build_gifu_url),
    Site("kani", "ミライブ", "🌲", "/static/images/miraibu.webp",
         providers.check_kani, providers.build_kani_url),
    Site("sanseido", "岐阜駅本屋", "📖", "/static/images/sanseido.webp",
         providers.check_sanseido, providers.build_sanseido_url),
    Site("tsutaya", "各務原BC", "☕", "/static/images/kakamigahara.webp",
         providers.check_tsutaya, lambda _kw: providers.TSUTAYA_FALLBACK_URL),
)


# ============================================================================
# TTL キャッシュ
# ============================================================================

class TTLCache:
    """スレッドセーフな、期限付きの小さなキャッシュ。

    同一キーワードの再検索（履歴ボタンの連打など）で
    各サイトへ再アクセスしないためのもの。
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if now - stored_at > self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


_cache = TTLCache(CACHE_TTL_SECONDS)


# ============================================================================
# 並列検索
# ============================================================================

async def _check_one(
    client: httpx.AsyncClient, site: Site, keyword: str
) -> models.SiteResult:
    """1サイトを検索する。想定外の例外もここで受け止め、他サイトを巻き込まない。"""
    try:
        status, url = await site.check(client, keyword)
    except Exception:
        logger.exception("%s: 予期しないエラー", site.key)
        status, url = models.ERROR, site.link(keyword)

    return models.SiteResult(
        key=site.key,
        name=site.name,
        icon=site.icon,
        status=status,
        url=url,
        image=site.image,
    )


async def search(keyword: str) -> Tuple[List[models.SiteResult], bool]:
    """全サイトを並列に検索する。

    Cloudflare Workers にはスレッドが無いため、ThreadPoolExecutor ではなく
    asyncio.gather で並行に走らせる。待ち時間の大半は通信待ちなので、
    スレッドを使わなくても同時に問い合わせられる。

    Returns:
        (結果リスト, キャッシュから返したか)
    """
    cached = _cache.get(keyword)
    if cached is not None:
        logger.info("キャッシュから返却: keyword=%r", keyword)
        return cached, True

    logger.info("検索開始: keyword=%r", keyword)
    started = time.monotonic()

    async with providers.new_client() as client:
        results = list(await asyncio.gather(
            *(_check_one(client, site, keyword) for site in SITES)
        ))

    elapsed = time.monotonic() - started
    logger.info(
        "検索完了 (%.2fs): %s",
        elapsed,
        " ".join(f"{r.name}={r.status.text}" for r in results),
    )

    # 全滅（ネットワーク断など）の結果はTTLの間残さず、次回すぐ再試行できるようにする
    if all(r.status == models.ERROR for r in results):
        logger.warning("全サイトがエラーのためキャッシュしない: keyword=%r", keyword)
        _cache.invalidate(keyword)
    else:
        _cache.set(keyword, results)

    return results, False
