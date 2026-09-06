"""アプリ本体のテスト。外部サイトへは一切アクセスしない。"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from book_search_app import auth, models, search
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
    # 検索履歴もサーバーからは出さない（端末の localStorage に持つ）
    assert "history-chips" in res.text and "chip\">" not in res.text


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


@pytest.mark.asyncio
async def test_search_uses_the_cache_and_does_not_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """同じキーワードの再検索で各サイトへ再アクセスしないこと。"""
    calls: list[str] = []

    async def fake_check(client, keyword: str) -> tuple[models.BookStatus, str]:
        calls.append(keyword)
        return models.AVAILABLE, "https://example.com/"

    fake_sites = tuple(
        search.Site(s.key, s.name, s.icon, s.image, fake_check, s.link) for s in search.SITES
    )
    monkeypatch.setattr(search, "SITES", fake_sites)
    monkeypatch.setattr(search, "_cache", search.TTLCache(600))

    first, cached_first = await search.search("テスト書名")
    second, cached_second = await search.search("テスト書名")

    assert cached_first is False and cached_second is True
    assert len(calls) == len(fake_sites), "2回目でサイトへ再アクセスしている"
    assert [r.status for r in second] == [r.status for r in first]


@pytest.mark.asyncio
async def test_all_error_results_are_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """全滅した結果を10分間持ち続けると、復旧しても失敗が返り続けてしまう。"""
    async def failing(client, keyword: str) -> tuple[models.BookStatus, str]:
        return models.ERROR, ""

    fake_sites = tuple(
        search.Site(s.key, s.name, s.icon, s.image, failing, s.link) for s in search.SITES
    )
    monkeypatch.setattr(search, "SITES", fake_sites)
    monkeypatch.setattr(search, "_cache", search.TTLCache(600))

    await search.search("通信断テスト")
    _, cached = await search.search("通信断テスト")
    assert cached is False, "エラーの結果がキャッシュされている"


@pytest.mark.asyncio
async def test_one_broken_site_does_not_break_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exploding(client, keyword: str) -> tuple[models.BookStatus, str]:
        raise RuntimeError("想定外の例外")

    async def healthy(client, keyword: str) -> tuple[models.BookStatus, str]:
        return models.AVAILABLE, "https://example.com/ok"

    # 残りのサイトも差し替える（テストから外部サイトへ出さないため）
    fake_sites = (
        search.Site("boom", "壊れるサイト", "💥", "", exploding, lambda kw: "https://example.com/"),
        *(search.Site(s.key, s.name, s.icon, s.image, healthy, s.link) for s in search.SITES[1:]),
    )
    monkeypatch.setattr(search, "SITES", fake_sites)
    monkeypatch.setattr(search, "_cache", search.TTLCache(600))

    results, _ = await search.search("例外テスト")
    assert results[0].status == models.ERROR
    assert results[0].url == "https://example.com/", "例外時もリンクは生きていること"
    assert all(r.status == models.AVAILABLE for r in results[1:]), "他サイトが巻き込まれている"


# ── TTLキャッシュ ───────────────────────────────────────────────

def test_ttl_cache_expires() -> None:
    cache = search.TTLCache(ttl_seconds=0)
    cache.set("k", "v")
    time.sleep(0.01)
    assert cache.get("k") is None


# ── HTML解析（Cloudflare Workers の CPU 10ms 制限に収めるため正規表現で行う）──

def test_first_work_id_extracts_from_search_html() -> None:
    from book_search_app.providers import _first_work_id

    html = (
        '<div><a class="x" href="/search/result/select?saleType=sell&amp;workId=41186860'
        '&amp;itemType=book">銀河鉄道の夜</a></div>'
    )
    assert _first_work_id(html) == "41186860"


def test_first_work_id_accepts_single_quoted_href() -> None:
    from book_search_app.providers import _first_work_id

    html = "<a href='/search/result/select?workId=123'>x</a>"
    assert _first_work_id(html) == "123"


def test_first_work_id_returns_none_when_absent() -> None:
    from book_search_app.providers import _first_work_id

    assert _first_work_id("<html><body>該当なし</body></html>") is None


def test_text_falls_back_to_utf8_when_charset_is_not_declared() -> None:
    """charset 宣言が無いと requests は ISO-8859-1 を既定にするため、
    そのときだけ UTF-8 とみなすことを固定する。"""
    import requests

    from book_search_app.providers import _text

    res = requests.Response()
    res._content = "在庫あり".encode("utf-8")
    res.encoding = "ISO-8859-1"
    assert _text(res) == "在庫あり"


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


# ── ログイン（公開ホスティングに置くための保護）──────────────────

def test_no_password_means_no_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """パスワード未設定なら手元の開発を邪魔しない。"""
    monkeypatch.delenv("BOOKFINDER_PASSWORD", raising=False)
    assert client.get("/").status_code == 200


def test_login_protects_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKFINDER_PASSWORD", "himitsu")
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_api_returns_401_instead_of_redirecting(monkeypatch: pytest.MonkeyPatch) -> None:
    """APIは画面遷移させず、フロントが扱える形で返す。"""
    monkeypatch.setenv("BOOKFINDER_PASSWORD", "himitsu")
    res = client.get("/api/pending")
    assert res.status_code == 401
    assert "error" in res.json()


@pytest.mark.parametrize("path", [
    "/manifest.webmanifest", "/sw.js", "/offline.html",
    "/favicon.ico", "/robots.txt", "/static/icons/icon-192.png",
])
def test_pwa_files_stay_public(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    """⚠️ ここを認証で塞ぐと PWA としてインストールできなくなる。"""
    monkeypatch.setenv("BOOKFINDER_PASSWORD", "himitsu")
    assert client.get(path).status_code == 200


def test_notify_stays_public_but_needs_its_own_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apps Script は Cookie を持たないので、Bearer トークンで守る。"""
    monkeypatch.setenv("BOOKFINDER_PASSWORD", "himitsu")
    res = client.post("/api/notify", json={"books": [{"title": "x"}]})
    # ログイン画面へのリダイレクトではなく、トークン不正の401であること
    assert res.status_code == 401
    assert res.json()["error"] == "unauthorized"


def test_correct_password_lets_you_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKFINDER_PASSWORD", "himitsu")
    monkeypatch.setenv("BOOKFINDER_SECURE_COOKIE", "0")

    bad = client.post("/login", data={"password": "chigau"}, follow_redirects=False)
    assert bad.headers["location"] == "/login?error=1"

    ok = client.post("/login", data={"password": "himitsu"}, follow_redirects=False)
    assert ok.headers["location"] == "/"
    assert auth.COOKIE_NAME in ok.cookies

    client.cookies.set(auth.COOKIE_NAME, ok.cookies[auth.COOKIE_NAME])
    assert client.get("/").status_code == 200
    client.cookies.clear()


def test_a_forged_cookie_is_rejected() -> None:
    assert auth.is_valid("9999999999.deadbeef") is False
    assert auth.is_valid(None) is False
    assert auth.is_valid("こわれている") is False
    assert auth.is_valid(auth.make_cookie_value()) is True


def test_login_locks_out_after_repeated_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """公開する以上、ログイン画面に無制限の試行をさせない。"""
    monkeypatch.setenv("BOOKFINDER_PASSWORD", "himitsu")
    auth._attempts.clear()

    for _ in range(auth.MAX_ATTEMPTS):
        client.post("/login", data={"password": "chigau"}, follow_redirects=False)

    # 上限に達したら、正しいパスワードでも一旦断る
    res = client.post("/login", data={"password": "himitsu"}, follow_redirects=False)
    assert res.headers["location"] == "/login?error=2"

    auth._attempts.clear()


# ── ストレージ抽象（Workers には FS が無いので差し替え可能にしてある）──

def test_push_and_pending_use_the_swappable_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """保存先を差し替えても動くこと。Workers では KV に差し替える。"""
    from book_search_app import pending, push, storage

    memory = storage.MemoryStore()
    monkeypatch.setattr(storage, "_store", memory)

    push.add({"endpoint": "https://example.com/x", "keys": {}})
    assert push.count() == 1
    assert memory.get(push.STORE_KEY)[0]["endpoint"] == "https://example.com/x"

    pending.add_many([{"library": "gifu", "title": "テスト本", "received": "2026-09-06"}])
    assert len(pending.load()) == 1
    assert memory.get(pending.STORE_KEY)[0]["title"] == "テスト本"


def test_file_store_survives_a_crash_mid_write(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """別名で書いてから差し替えるので、既存ファイルが壊れない。"""
    from book_search_app import storage

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    store = storage.FileStore()
    store.set("things", [1, 2, 3])
    assert store.get("things") == [1, 2, 3]
    assert not list(tmp_path.glob("*.tmp")), "一時ファイルが残っている"


# ── 受取期限の決め方 ────────────────────────────────────────────

def test_kani_uses_the_date_written_in_the_mail() -> None:
    from datetime import date

    from book_search_app.pending import deadline_for

    due, is_estimate = deadline_for("kani", date(2026, 3, 26), "2026/04/05")
    assert due == "2026-04-05"
    assert is_estimate is False


def test_gifu_falls_back_to_the_earliest_possible_deadline() -> None:
    """「連絡日の翌日から7開館日」は正確に計算できないので安全側に倒す。

    休館日があれば実際の期限は後ろへずれるだけなので、
    この日までに行けば必ず間に合う。
    """
    from datetime import date

    from book_search_app.pending import deadline_for

    due, is_estimate = deadline_for("gifu", date(2026, 4, 5), None)
    assert due == "2026-04-12"
    assert is_estimate is True


def test_the_same_book_is_not_registered_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """同じメールを二度拾っても増やさない。"""
    from book_search_app import pending, storage

    monkeypatch.setattr(storage, "_store", storage.MemoryStore())
    entry = {"library": "gifu", "title": "同じ本", "received": "2026-09-06"}
    pending.add_many([entry])
    pending.add_many([entry])
    assert len(pending.load()) == 1
