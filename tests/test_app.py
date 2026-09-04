"""アプリ本体のテスト。外部サイトへは一切アクセスしない。"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from book_search_app import models, search
from book_search_app.main import app
from book_search_app.providers import (
    build_amazon_url,
    build_gifu_url,
    build_kani_url,
    build_sanseido_url,
)

client = TestClient(app)


# ── ルーティング ────────────────────────────────────────────────

def test_index_returns_html() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Book Finder" in res.text
    # 検索結果は初期HTMLに含めない（外部サイトの応答を待たずに画面を出すため）
    assert "results-grid" not in res.text


def test_manifest_content_type() -> None:
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/manifest+json"


def test_service_worker_is_served_at_root_with_scope_header() -> None:
    """SW がルートスコープを取れること（PWA_GUIDE §7）。"""
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert res.headers["service-worker-allowed"] == "/"
    # no-cache が無いと端末に古いSWが残り続ける
    assert res.headers["cache-control"] == "no-cache"


def test_offline_page_is_served() -> None:
    res = client.get("/offline.html")
    assert res.status_code == 200
    assert "オフライン" in res.text


# ── 検索API ─────────────────────────────────────────────────────

def test_search_requires_a_keyword() -> None:
    res = client.get("/api/search", params={"q": "   "})
    assert res.status_code == 400
    assert "error" in res.json()


def test_search_rejects_an_overlong_keyword() -> None:
    res = client.get("/api/search", params={"q": "あ" * 200})
    assert res.status_code == 400
    assert "error" in res.json()


def test_search_uses_the_cache_and_does_not_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """同じキーワードの再検索で各サイトへ再アクセスしないこと。"""
    calls: list[str] = []

    def fake_check(keyword: str) -> tuple[models.BookStatus, str]:
        calls.append(keyword)
        return models.AVAILABLE, "https://example.com/"

    fake_sites = tuple(
        search.Site(s.key, s.name, s.icon, s.image, fake_check, s.link) for s in search.SITES
    )
    monkeypatch.setattr(search, "SITES", fake_sites)
    monkeypatch.setattr(search, "_cache", search.TTLCache(600))

    first, cached_first = search.search("テスト書名")
    second, cached_second = search.search("テスト書名")

    assert cached_first is False and cached_second is True
    assert len(calls) == len(fake_sites), "2回目でサイトへ再アクセスしている"
    assert [r.status for r in second] == [r.status for r in first]


def test_all_error_results_are_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """全滅した結果を10分間持ち続けると、復旧しても失敗が返り続けてしまう。"""
    def failing(keyword: str) -> tuple[models.BookStatus, str]:
        return models.ERROR, ""

    fake_sites = tuple(
        search.Site(s.key, s.name, s.icon, s.image, failing, s.link) for s in search.SITES
    )
    monkeypatch.setattr(search, "SITES", fake_sites)
    monkeypatch.setattr(search, "_cache", search.TTLCache(600))

    search.search("通信断テスト")
    _, cached = search.search("通信断テスト")
    assert cached is False, "エラーの結果がキャッシュされている"


def test_one_broken_site_does_not_break_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding(keyword: str) -> tuple[models.BookStatus, str]:
        raise RuntimeError("想定外の例外")

    def healthy(keyword: str) -> tuple[models.BookStatus, str]:
        return models.AVAILABLE, "https://example.com/ok"

    # 残りのサイトも差し替える（テストから外部サイトへ出さないため）
    fake_sites = (
        search.Site("boom", "壊れるサイト", "💥", "", exploding, lambda kw: "https://example.com/"),
        *(search.Site(s.key, s.name, s.icon, s.image, healthy, s.link) for s in search.SITES[1:]),
    )
    monkeypatch.setattr(search, "SITES", fake_sites)
    monkeypatch.setattr(search, "_cache", search.TTLCache(600))

    results, _ = search.search("例外テスト")
    assert results[0].status == models.ERROR
    assert results[0].url == "https://example.com/", "例外時もリンクは生きていること"
    assert all(r.status == models.AVAILABLE for r in results[1:]), "他サイトが巻き込まれている"


# ── TTLキャッシュ ───────────────────────────────────────────────

def test_ttl_cache_expires() -> None:
    cache = search.TTLCache(ttl_seconds=0)
    cache.set("k", "v")
    time.sleep(0.01)
    assert cache.get("k") is None


# ── URLビルダー（リクエストは送らない）──────────────────────────

@pytest.mark.parametrize(
    "builder,host",
    [
        (build_gifu_url, "www1.gifu-lib.jp"),
        (build_kani_url, "www.kani-lib.jp"),
        (build_sanseido_url, "www.books-sanseido.jp"),
        (build_amazon_url, "www.amazon.co.jp"),
    ],
)
def test_url_builders_escape_the_keyword(builder, host: str) -> None:
    url = builder("坊っちゃん & 夏目")
    assert url.startswith(f"https://{host}/")
    # 生の空白や & がクエリに混ざらないこと
    assert " " not in url
    assert "%26" in url or "&" in url.split("?", 1)[1]
