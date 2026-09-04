"""各サイトの在庫チェックと検索URLの生成。

このモジュールだけが外部サイトへHTTPリクエストを送る。
リクエストの作法（robots.txt の遵守・User-Agent の明示・
アクセス回数の抑制）はここに集約している。
詳細は docs/README.md「スクレイピングポリシー」を参照。
"""

from __future__ import annotations

import logging
import re
import threading
import urllib.parse
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

from . import models
from .config import (
    HEADERS,
    KUSA_BOOKS_KEYWORD,
    TIMEOUT_MEDIUM,
    TIMEOUT_SHORT,
)

logger = logging.getLogger(__name__)

# requests.Session はスレッドセーフではないため、スレッドごとに1つ持つ。
# コネクションを使い回すぶん、同一スレッドでの2回目以降が速くなる。
_local = threading.local()


def _session() -> requests.Session:
    """このスレッド用の Session を返す（無ければ作る）。"""
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _local.session = session
    return session


# ============================================================================
# 検索URLビルダー（リクエストは送らない。ユーザーのブラウザが開くためのURL）
# ============================================================================

def build_gifu_url(keyword: str) -> str:
    """メディコス（岐阜市立図書館）の検索URL。"""
    return (
        "https://www1.gifu-lib.jp/winj/opac/search-standard.do?"
        + urllib.parse.urlencode(
            {
                "lang": "ja",
                "txt_word": keyword,
                "hid_word_column": "fulltext",
                "submit_btn_searchEasy": "search",
            }
        )
    )


def build_kani_url(keyword: str) -> str:
    """ミライブ（可児市立図書館）の検索URL。"""
    return (
        "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP?"
        + urllib.parse.urlencode(
            {
                "opr(1)": "OR",
                "DB": "LIB",
                "PID": "OPWSRCH1",
                "FLG": "SEARCH",
                "MODE": "1",
                "SORT": "-3",
                "qual(1)": "MZALL",
                "text(1)": keyword,
            }
        )
    )


_SANSEIDO_PARAMS = {
    "shopCode": "0458",
    "defaultShopCode": "",
    "title": "",
    "author": "",
    "isbn": "",
    "genreCode": "",
    "search": "検索",
}

def build_sanseido_url(keyword: str) -> str:
    """岐阜駅本屋（三省堂）の検索URL。"""
    return (
        "https://www.books-sanseido.jp/booksearch/BookSearchExec.action?"
        + urllib.parse.urlencode(_SANSEIDO_PARAMS | {"keyword": keyword})
    )


TSUTAYA_FALLBACK_URL = "https://store-tsutaya.tsite.jp/search/?sheader_item-search"


# ============================================================================
# メディコス（岐阜市立図書館）
# ============================================================================

_GIFU_NO_HIT_PHRASES = (
    "該当する資料はありません",
    "該当するリストが存在しません",
)


def check_gifu(keyword: str) -> Tuple[models.BookStatus, str]:
    """メディコスの在庫をチェックする。"""
    url = build_gifu_url(keyword)
    logger.info("メディコスを検索: '%s'", keyword)
    try:
        session = _session()

        # 検索前にトップを1回叩いてセッションを確立する（この OPAC の仕様）
        session.get("https://www1.gifu-lib.jp/winj/opac/top.do", timeout=TIMEOUT_SHORT)

        res = session.get(
            "https://www1.gifu-lib.jp/winj/opac/search-standard.do",
            params={
                "txt_word": keyword,
                "hid_word_column": "fulltext",
                "submit_btn_searchEasy": "search",
            },
            timeout=TIMEOUT_SHORT,
            allow_redirects=True,
        )
        res.encoding = res.apparent_encoding

        if "g-mediacosmos.jp" in res.url or any(p in res.text for p in _GIFU_NO_HIT_PHRASES):
            logger.info("メディコス: 該当なし")
            return models.NONE_FOUND, url

        logger.info("メディコス: 在庫あり")
        return models.AVAILABLE, url

    except requests.exceptions.Timeout:
        logger.warning("メディコス: タイムアウト (keyword=%r)", keyword)
        return models.ERROR, url
    except requests.exceptions.RequestException as exc:
        logger.error("メディコス: リクエストエラー - %s", exc)
        return models.ERROR, url


# ============================================================================
# ミライブ（可児市立図書館）
# ============================================================================

def check_kani(keyword: str) -> Tuple[models.BookStatus, str]:
    """ミライブは自動アクセスせず、検索結果ページへのリンクだけを返す。

    kani-lib.jp の robots.txt は検索パス `/csp` 配下を Disallow しており、
    2026-05-11 には「サーバ負荷軽減」の注記も追加されている。これを尊重し、
    在庫の自動判定は行わない。リンクを開くリクエストを送るのは
    利用者自身のブラウザなので、アプリは同館へ一度もアクセスしない。

    自動判定を復活させる場合はカーリル図書館API（無償・商用可）を使うこと。
    詳細: docs/scraping_monetization_report.md
    """
    logger.info("ミライブ: robots.txt 尊重のため自動アクセスなし (keyword=%r)", keyword)
    return models.LINK_ONLY, build_kani_url(keyword)


# ============================================================================
# 岐阜駅本屋（三省堂）
# ============================================================================

_SANSEIDO_TOTAL_RE = re.compile(r"<strong>\s*(\d+)\s*</strong>\s*件中")
_SANSEIDO_STOCK_RE = re.compile(r"在庫：\s*([○×△▲])")


def check_sanseido(keyword: str) -> Tuple[models.BookStatus, str]:
    """岐阜駅本屋の在庫をチェックする（書籍のみ。電子書籍は在庫に含めない）。"""
    url = build_sanseido_url(keyword)
    logger.info("岐阜駅本屋を検索: '%s'", keyword)
    try:
        res = _session().get(
            "https://www.books-sanseido.jp/booksearch/BookSearchExec.action",
            params=_SANSEIDO_PARAMS | {"keyword": keyword},
            timeout=TIMEOUT_SHORT,
        )
        res.encoding = res.apparent_encoding

        if "検索結果：0件" in res.text or "検索結果:0件" in res.text:
            logger.info("岐阜駅本屋: 該当なし")
            return models.NONE_FOUND, url

        match = _SANSEIDO_TOTAL_RE.search(res.text)
        total = int(match.group(1)) if match else None
        if total == 0:
            logger.info("岐阜駅本屋: 該当なし（0件）")
            return models.NONE_FOUND, url

        # 在庫記号: ○=書籍在庫あり, ×=なし, △/▲=電子書籍等
        marks = _SANSEIDO_STOCK_RE.findall(res.text)
        if marks:
            if "○" in marks:
                logger.info("岐阜駅本屋: 在庫あり（書籍）")
                return models.AVAILABLE, url
            logger.info("岐阜駅本屋: 在庫なし（書籍は×のみ、または△/▲のみ）")
            return models.NONE_FOUND, url

        if total:
            logger.info("岐阜駅本屋: %d 件ヒット（在庫詳細不明）", total)
            return models.hit_count(total), url

        logger.warning("岐阜駅本屋: 判定できなかった (keyword=%r)", keyword)
        return models.PENDING, url

    except requests.exceptions.Timeout:
        logger.warning("岐阜駅本屋: タイムアウト (keyword=%r)", keyword)
        return models.ERROR, url
    except requests.exceptions.RequestException as exc:
        logger.error("岐阜駅本屋: リクエストエラー - %s", exc)
        return models.ERROR, url


# ============================================================================
# 各務原BC（草叢BOOKS / TSUTAYA）
# ============================================================================

_WORK_ID_RE = re.compile(r"workId=(\d+)")
_PRODUCT_KEY_RE = re.compile(r"productKey=(\d+)")
_PRODUCT_KEY_IN_URL_RE = re.compile(r"/\d+/(\d{10,13})\b")


def _first_work_id(html: str) -> Optional[str]:
    """検索結果HTMLから1位の workId を抜き出す。"""
    soup = BeautifulSoup(html, "html.parser")
    anchor = soup.find("a", href=re.compile(r"/search/result/select\?"))
    if not anchor:
        return None
    href = anchor.get("href") or ""
    match = _WORK_ID_RE.search(href)
    return match.group(1) if match else None


def _product_key(work_id: str) -> Optional[str]:
    """select ページから productKey（ISBN/JAN）を抜き出す。"""
    try:
        res = _session().get(
            "https://store-tsutaya.tsite.jp/search/result/select",
            params={"saleType": "sell", "workId": work_id, "itemType": "book"},
            timeout=TIMEOUT_MEDIUM,
            allow_redirects=True,
        )
    except requests.exceptions.RequestException as exc:
        logger.error("productKey 取得エラー (work_id=%s): %s", work_id, exc)
        return None

    match = _PRODUCT_KEY_RE.search(res.text)
    if match:
        return match.group(1)
    match = _PRODUCT_KEY_IN_URL_RE.search(res.url)
    return match.group(1) if match else None


def _tsutaya_urls(keyword: str) -> Tuple[str, str]:
    """(検索URL, 在庫確認URL) を返す。特定できなければ両方とも検索URL。"""
    search_url = (
        "https://store-tsutaya.tsite.jp/search/result/"
        f"?keyword={urllib.parse.quote(keyword)}&itemType=book&limit=20"
    )
    try:
        res = _session().get(search_url, timeout=TIMEOUT_MEDIUM)
        work_id = _first_work_id(res.text)
        if not work_id:
            logger.debug("各務原BC: workId が取得できなかった (keyword=%r)", keyword)
            return search_url, search_url

        product_key = _product_key(work_id)
        if not product_key:
            logger.debug("各務原BC: productKey が取得できなかった (work_id=%s)", work_id)
            return search_url, search_url

        stock_url = (
            "https://store-tsutaya.tsite.jp/search/result/stock/result"
            f"?workId={work_id}&saleType=sell&itemType=book&productKey={product_key}"
            f"&storeSearchKeyword={urllib.parse.quote(KUSA_BOOKS_KEYWORD)}"
        )
        return search_url, stock_url

    except requests.exceptions.RequestException as exc:
        logger.error("各務原BC URL 生成エラー: %s", exc)
        return search_url, search_url


def check_tsutaya(keyword: str) -> Tuple[models.BookStatus, str]:
    """各務原BCの在庫をチェックする。"""
    logger.info("各務原BCを検索: '%s'", keyword)
    search_url, stock_url = _tsutaya_urls(keyword)

    if search_url == stock_url:
        return models.PENDING, stock_url

    try:
        res = _session().get(stock_url, timeout=TIMEOUT_MEDIUM)
        res.encoding = res.apparent_encoding

        if "在庫あり" in res.text:
            logger.info("各務原BC: 在庫あり")
            return models.AVAILABLE, stock_url
        if "在庫なし" in res.text or "入荷予定は店舗にお問い合わせ下さい" in res.text:
            logger.info("各務原BC: 在庫なし")
            return models.NONE_FOUND, stock_url

        logger.info("各務原BC: 判定保留")
        return models.PENDING, stock_url

    except requests.exceptions.Timeout:
        logger.warning("各務原BC: タイムアウト (keyword=%r)", keyword)
        return models.ERROR, search_url
    except requests.exceptions.RequestException as exc:
        logger.error("各務原BC: リクエストエラー - %s", exc)
        return models.ERROR, TSUTAYA_FALLBACK_URL


def build_amazon_url(keyword: str) -> str:
    """Amazon の書籍検索URL。"""
    return "https://www.amazon.co.jp/s?" + urllib.parse.urlencode(
        {"k": keyword, "i": "stripbooks"}
    )
