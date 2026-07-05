"""
書籍横断検索アプリ

メディコス・ミライブ・岐阜駅本屋・各務原BCを一括検索する
Streamlit アプリケーション
"""

# ============================================================================
# 標準ライブラリ
# ============================================================================
import base64
import logging
import logging.handlers
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

# ============================================================================
# サードパーティライブラリ
# ============================================================================
import requests
import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup


# ============================================================================
# ロギング設定
# ============================================================================

def _setup_logger(name: str = "book_finder") -> logging.Logger:
    """アプリケーション用ロガーを設定して返す。"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = _setup_logger()


# ============================================================================
# データクラス
# ============================================================================

@dataclass(frozen=True)
class BookStatus:
    """各サイトの在庫状況を表す不変データクラス。"""
    text: str
    css_class: str
    icon: str


# ============================================================================
# 設定・定数
# ============================================================================

st.set_page_config(page_title="Book Finder", layout="wide", page_icon="📚")

# HTTP リクエスト設定
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "BookFinder/1.0 (personal-use)"
)
HEADERS: Dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
TIMEOUT_SHORT: int = 10
TIMEOUT_MEDIUM: int = 20

# アプリ設定
HISTORY_LIMIT: int = 5
KUSA_BOOKS_KEYWORD: str = "各務原店"
# 同一キーワードの再検索で各サイトへ再アクセスしない猶予時間（サーバー負荷軽減）
CACHE_TTL_SECONDS: int = 600

# 在庫ステータス定数
_S_AVAILABLE = BookStatus("在庫あり", "accent-ok",   "⭕️")
_S_NONE      = BookStatus("なし",     "accent-ng",   "❌")
_S_LENDING   = BookStatus("貸出中",   "accent-warn", "⚠️")
_S_PENDING   = BookStatus("判定保留", "accent-warn", "⚠️")
_S_ERROR     = BookStatus("エラー",   "accent-warn", "⚠️")
_S_LINK_ONLY = BookStatus("リンクで確認", "accent-warn", "🔗")

# 静的アセット
_APP_DIR: Path = Path(__file__).parent
_STATIC_DIR: Path = _APP_DIR / "static"
_IMAGES_DIR: Path = _STATIC_DIR / "images"

CARD_BG_PATHS: Dict[str, Path] = {
    "gifu":     _IMAGES_DIR / "メディコス.webp",
    "kani":     _IMAGES_DIR / "ミライブ.webp",
    "sanseido": _IMAGES_DIR / "岐阜駅本屋.png",
    "tsutaya":  _IMAGES_DIR / "各務原BC.jpg",
}

_BG_IMAGE_PATH: Path = _IMAGES_DIR / "松本十畳.jpg"


# ============================================================================
# 画像・CSS ローダー（キャッシュ付き）
# ============================================================================

@st.cache_resource
def _load_bg_base64() -> str:
    """背景画像（松本十畳）を base64 で返す。"""
    try:
        with open(_BG_IMAGE_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        logger.warning("背景画像が見つかりません: %s", _BG_IMAGE_PATH)
        return ""


def _mime_for_path(p: Path) -> str:
    """拡張子から data URI 用の MIME タイプを返す。"""
    s = p.suffix.lower()
    if s == ".webp":
        return "image/webp"
    if s == ".png":
        return "image/png"
    return "image/jpeg"


@st.cache_resource
def _load_card_images_base64() -> Dict[str, str]:
    """4枚のカード背景画像を data URI 文字列の辞書で返す。"""
    out: Dict[str, str] = {}
    for key, path in CARD_BG_PATHS.items():
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = _mime_for_path(path)
            out[key] = f"data:{mime};base64,{b64}"
        except FileNotFoundError:
            logger.warning("カード画像が見つかりません: %s", path)
            out[key] = ""
    return out


# ============================================================================
# CSS ビルダー（キャッシュ付き — Bug1 修正の核心）
# ============================================================================

_CSS_DIR: Path = _STATIC_DIR / "css"
_CSS_FILES: tuple[str, ...] = (
    "variables.css",
    "layout.css",
    "forms.css",
    "cards.css",
    "loading.css",
    "responsive.css",
)


def _build_app_css(bg_base64: str) -> str:
    """
    アプリ全体の CSS を組み立てて返す（キャッシュ済み）。

    初回ロード以降はキャッシュから即座に返却されるため、
    CSS ファイル読み込みの遅延による表示の不安定さを解消する。
    """
    if bg_base64:
        bg_layer = f'url("data:image/jpeg;base64,{bg_base64}")'
    else:
        bg_layer = "none"

    parts: list[str] = []
    for name in _CSS_FILES:
        path = _CSS_DIR / name
        try:
            content = path.read_text(encoding="utf-8")
            content = content.replace("__BG_LAYER__", bg_layer)
            parts.append(content)
        except FileNotFoundError:
            logger.warning("CSS ファイルが見つかりません: %s", path)

    return f"<style>\n" + "\n".join(parts) + "\n</style>"


# ============================================================================
# ユーティリティ関数
# ============================================================================

def _init_session_state() -> None:
    """セッションステートを初期化する。"""
    if "search_history" not in st.session_state:
        st.session_state.search_history = []


def _add_to_history(keyword: str) -> None:
    """検索履歴にキーワードを追加する（最大 HISTORY_LIMIT 件）。"""
    if not keyword:
        return
    history: list = st.session_state.search_history
    if keyword in history:
        history.remove(keyword)
    history.insert(0, keyword)
    st.session_state.search_history = history[:HISTORY_LIMIT]


# ============================================================================
# 各サイトの在庫チェック関数
# ============================================================================

def check_gifu_lib(keyword: str) -> BookStatus:
    """メディコス（岐阜市立図書館）の在庫をチェックする。"""
    logger.info("メディコスを検索: '%s'", keyword)
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        session.get(
            "https://www1.gifu-lib.jp/winj/opac/top.do",
            timeout=TIMEOUT_SHORT,
        )

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

        no_hit_phrases = (
            "該当する資料はありません",
            "該当するリストが存在しません",
        )
        if "g-mediacosmos.jp" in res.url or any(p in res.text for p in no_hit_phrases):
            logger.info("メディコス: 該当なし")
            return _S_NONE

        logger.info("メディコス: 在庫あり")
        return _S_AVAILABLE

    except requests.exceptions.Timeout:
        logger.warning("メディコス: タイムアウト (keyword='%s')", keyword)
        return _S_ERROR
    except requests.exceptions.RequestException as exc:
        logger.error("メディコス: リクエストエラー - %s", exc)
        return _S_ERROR


def check_kani_lib(keyword: str) -> BookStatus:
    """ミライブ（可児市立図書館）は自動アクセスせず、リンク提示のみ。

    kani-lib.jp の robots.txt は検索パス `/csp` 配下を Disallow しており、
    2026-05-11 には「サーバ負荷軽減」の注記も追加されている。これを尊重し、
    在庫の自動判定は行わず、検索結果ページへのリンクだけを提供する。
    自動判定を復活させる場合はカーリル図書館API（無償・商用可）を使うこと。
    詳細: docs/scraping_monetization_report.md
    """
    logger.info("ミライブ: robots.txt 尊重のため自動アクセスなし (keyword='%s')", keyword)
    return _S_LINK_ONLY


def check_sanseido(keyword: str) -> BookStatus:
    """岐阜駅本屋の在庫をチェックする（書籍のみ。電子書籍は在庫に含めない）。"""
    logger.info("岐阜駅本屋を検索: '%s'", keyword)
    try:
        res = requests.get(
            "https://www.books-sanseido.jp/booksearch/BookSearchExec.action",
            params={
                "shopCode":        "0458",
                "keyword":         keyword,
                "defaultShopCode": "",
                "title":           "",
                "author":          "",
                "isbn":            "",
                "genreCode":       "",
                "search":          "検索",
            },
            headers=HEADERS,
            timeout=TIMEOUT_SHORT,
        )
        res.encoding = res.apparent_encoding

        if "検索結果：0件" in res.text or "検索結果:0件" in res.text:
            logger.info("岐阜駅本屋: 該当なし")
            return _S_NONE

        match = re.search(r"<strong>\s*(\d+)\s*</strong>\s*件中", res.text)
        total = int(match.group(1)) if match else None
        if total == 0:
            logger.info("岐阜駅本屋: 該当なし（0件）")
            return _S_NONE

        # 在庫記号: ○=書籍在庫あり, ×=なし, △/▲=電子書籍等
        stock_marks = re.findall(r"在庫：\s*([○×△▲])", res.text)
        if stock_marks:
            if any(mark == "○" for mark in stock_marks):
                logger.info("岐阜駅本屋: 在庫あり（書籍）")
                return _S_AVAILABLE
            logger.info("岐阜駅本屋: 在庫なし（書籍は×のみ、または△/▲のみ）")
            return _S_NONE

        if total is not None and total > 0:
            logger.info("岐阜駅本屋: %d 件ヒット（在庫詳細不明）", total)
            return BookStatus(f"{total}件", "accent-warn", "⚠️")

        logger.warning("岐阜駅本屋: 判定できなかった (keyword='%s')", keyword)
        return _S_PENDING

    except requests.exceptions.Timeout:
        logger.warning("岐阜駅本屋: タイムアウト (keyword='%s')", keyword)
        return _S_ERROR
    except requests.exceptions.RequestException as exc:
        logger.error("岐阜駅本屋: リクエストエラー - %s", exc)
        return _S_ERROR


# ── 各務原BC（TSUTAYA）ヘルパー ──────────────────────────────────────────────

def _extract_first_tsutaya_work_id(html: str) -> Optional[str]:
    """検索結果 HTML から1位の workId を抽出する。"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        anchor = soup.find("a", href=re.compile(r"/search/result/select\?"))
        if not anchor or not anchor.get("href"):
            return None
        match = re.search(r"workId=(\d+)", anchor["href"])
        return match.group(1) if match else None
    except Exception as exc:
        logger.error("workId 抽出エラー: %s", exc)
        return None


def _extract_tsutaya_product_key(work_id: str) -> Optional[str]:
    """select ページから productKey（ISBN/JAN）を抽出する。"""
    try:
        res = requests.get(
            "https://store-tsutaya.tsite.jp/search/result/select",
            params={
                "saleType": "sell",
                "workId":   work_id,
                "itemType": "book",
            },
            headers=HEADERS,
            timeout=TIMEOUT_MEDIUM,
            allow_redirects=True,
        )
        match = re.search(r"productKey=(\d+)", res.text)
        if match:
            return match.group(1)
        match2 = re.search(r"/\d+/(\d{10,13})\b", res.url)
        return match2.group(1) if match2 else None
    except requests.exceptions.RequestException as exc:
        logger.error("productKey 取得エラー (work_id=%s): %s", work_id, exc)
        return None


def _build_tsutaya_stock_url(keyword: str) -> Tuple[str, str]:
    """検索 URL と在庫確認 URL を生成する。"""
    search_url = (
        "https://store-tsutaya.tsite.jp/search/result/"
        f"?keyword={urllib.parse.quote(keyword)}&itemType=book&limit=20"
    )
    try:
        res = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT_MEDIUM)
        work_id = _extract_first_tsutaya_work_id(res.text)
        if not work_id:
            logger.debug("各務原BC: workId が取得できなかった (keyword='%s')", keyword)
            return search_url, search_url

        product_key = _extract_tsutaya_product_key(work_id)
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


def check_tsutaya(keyword: str) -> Tuple[BookStatus, str]:
    """各務原BCの在庫をチェックする。"""
    logger.info("各務原BCを検索: '%s'", keyword)
    search_url, stock_url = _build_tsutaya_stock_url(keyword)

    if search_url == stock_url:
        return _S_PENDING, stock_url

    try:
        res = requests.get(stock_url, headers=HEADERS, timeout=TIMEOUT_MEDIUM)
        res.encoding = res.apparent_encoding

        if "在庫あり" in res.text:
            logger.info("各務原BC: 在庫あり")
            return _S_AVAILABLE, stock_url
        if "在庫なし" in res.text or "入荷予定は店舗にお問い合わせ下さい" in res.text:
            logger.info("各務原BC: 在庫なし")
            return _S_NONE, stock_url

        logger.info("各務原BC: 判定保留")
        return _S_PENDING, stock_url

    except requests.exceptions.Timeout:
        logger.warning("各務原BC: タイムアウト (keyword='%s')", keyword)
        return _S_ERROR, search_url
    except requests.exceptions.RequestException as exc:
        logger.error("各務原BC: リクエストエラー - %s", exc)
        return (
            _S_ERROR,
            "https://store-tsutaya.tsite.jp/search/?sheader_item-search",
        )


# ============================================================================
# 一括検索（並列実行）
# ============================================================================

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def check_all_sites(keyword: str) -> Dict[str, object]:
    """
    全4サイトの在庫を並列にチェックする。

    ThreadPoolExecutor で4サイトを同時リクエストし、
    逐次実行に比べて大幅に応答時間を短縮する。

    結果は CACHE_TTL_SECONDS の間キャッシュされ、同一キーワードの
    再検索（履歴ボタン連打など）で各サイトへ再アクセスしない。
    そのぶん在庫表示が最大10分ほど古い可能性がある。

    Returns:
        {
            "gifu": BookStatus,
            "kani": BookStatus,
            "sanseido": BookStatus,
            "tsutaya": (BookStatus, url),
        }
    """
    results: Dict[str, object] = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(check_gifu_lib, keyword): "gifu",
            executor.submit(check_kani_lib, keyword): "kani",
            executor.submit(check_sanseido, keyword): "sanseido",
            executor.submit(check_tsutaya, keyword): "tsutaya",
        }
        for future in as_completed(futures):
            site_key = futures[future]
            try:
                results[site_key] = future.result()
            except Exception as exc:
                logger.error("%s: 予期しないエラー - %s", site_key, exc)
                if site_key == "tsutaya":
                    results[site_key] = (
                        _S_ERROR,
                        "https://store-tsutaya.tsite.jp/search/?sheader_item-search",
                    )
                else:
                    results[site_key] = _S_ERROR

    return results


# ============================================================================
# URL ビルダー関数
# ============================================================================

def build_gifu_url(keyword: str) -> str:
    """メディコス（岐阜市立図書館）の検索 URL を生成する。"""
    return (
        "https://www1.gifu-lib.jp/winj/opac/search-standard.do?"
        + urllib.parse.urlencode({
            "lang":                  "ja",
            "txt_word":              keyword,
            "hid_word_column":       "fulltext",
            "submit_btn_searchEasy": "search",
        })
    )


def build_kani_url(keyword: str) -> str:
    """ミライブ（可児市立図書館）の検索 URL を生成する。"""
    return (
        "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP?"
        + urllib.parse.urlencode({
            "opr(1)":  "OR",
            "DB":      "LIB",
            "PID":     "OPWSRCH1",
            "FLG":     "SEARCH",
            "MODE":    "1",
            "SORT":    "-3",
            "qual(1)": "MZALL",
            "text(1)": keyword,
        })
    )


def build_sanseido_url(keyword: str) -> str:
    """岐阜駅本屋の検索 URL を生成する。"""
    return (
        "https://www.books-sanseido.jp/booksearch/BookSearchExec.action?"
        + urllib.parse.urlencode({
            "shopCode":        "0458",
            "keyword":         keyword,
            "defaultShopCode": "",
            "title":           "",
            "author":          "",
            "isbn":            "",
            "genreCode":       "",
            "search":          "検索",
        })
    )


def build_amazon_url(keyword: str) -> str:
    """Amazon の書籍検索 URL を生成する。"""
    return (
        "https://www.amazon.co.jp/s?"
        + urllib.parse.urlencode({"k": keyword, "i": "stripbooks"})
    )


# ============================================================================
# UI 生成関数
# ============================================================================

_PILL_CLASS_MAP: Dict[str, str] = {
    "accent-ok":   "pill-ok",
    "accent-ng":   "pill-ng",
    "accent-warn": "pill-warn",
}


def _create_result_card(
    site_name: str,
    icon: str,
    status: BookStatus,
    url: str,
    bg_image_url: str = "",
) -> str:
    """検索結果カードの HTML を生成する。"""
    pill_class = _PILL_CLASS_MAP.get(status.css_class, "pill-warn")
    if bg_image_url:
        bg_style = f"background-image: url('{bg_image_url}');"
    else:
        bg_style = "background: linear-gradient(160deg, #1a1040 0%, #0c0820 100%);"
    return (
        f'<div class="result-card {status.css_class}" style="{bg_style}">'
        f'  <div class="card-overlay"></div>'
        f'  <div class="card-content">'
        f'    <div class="card-top">'
        f'      <div class="site">'
        f'        <span class="site-icon">{icon}</span>'
        f'        <span class="site-title">{site_name}</span>'
        f'      </div>'
        f'      <div class="status-pill {pill_class}">{status.icon} {status.text}</div>'
        f'    </div>'
        f'    <a href="{url}" target="_blank" rel="noopener noreferrer" class="btn-link">'
        f'      結果を開く ↗'
        f'    </a>'
        f'  </div>'
        f'</div>'
    )


def _render_search_history() -> None:
    """検索履歴ボタンを表示する。"""
    if not st.session_state.search_history:
        return
    st.caption("🕒 検索履歴:")
    cols = st.columns(HISTORY_LIMIT)
    for i, hist_kw in enumerate(st.session_state.search_history[:HISTORY_LIMIT]):
        if cols[i].button(hist_kw, key=f"h_{i}", use_container_width=True):
            # keyword_input はウィジェット生成後に直接書き換えられない
            # （StreamlitAPIException になる）ため、次回 run の生成前に反映する
            st.session_state.pending_keyword = hist_kw
            st.rerun()


def _render_amazon_button() -> None:
    """
    Amazon 検索ボタンを components.html で描画する（Bug2 修正）。

    Streamlit の st.markdown では JavaScript が除去されるため、
    components.html を使い、クリック時に親ドキュメントの入力欄から
    リアルタイムにキーワードを取得して Amazon URL を構築する。
    これにより、Enter キーを押さずに直接ボタンをクリックしても
    入力中のキーワードが正しく反映される。
    """
    components.html(
        """
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { background: transparent !important; }
            a.btn-amazon {
                display: flex !important;
                width: 100% !important;
                text-align: center !important;
                color: #0C0800 !important;
                text-decoration: none !important;
                border-radius: 14px !important;
                font-weight: 900 !important;
                padding: 0.75rem 1rem !important;
                min-height: 50px !important;
                align-items: center !important;
                justify-content: center !important;
                box-shadow: 0 10px 28px rgba(52, 211, 153, 0.28) !important;
                transition: transform 0.15s ease, box-shadow 0.15s ease !important;
                line-height: 1.4 !important;
                background: linear-gradient(135deg, #34d399 0%, #10b981 100%) !important;
                border: none !important;
                margin: 0 !important;
                letter-spacing: 0.01em !important;
                font-size: 0.97rem !important;
                cursor: pointer;
                font-family: ui-sans-serif, system-ui, -apple-system,
                             "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            }
            a.btn-amazon:hover {
                transform: translateY(-2px) !important;
                box-shadow: 0 16px 36px rgba(52, 211, 153, 0.38) !important;
                filter: brightness(1.06) !important;
                color: #0C0800 !important;
            }
        </style>
        <a href="#" class="btn-amazon" onclick="
            var inputs = window.parent.document.querySelectorAll(
                'input[type=text], input[aria-label]'
            );
            var kw = '';
            for (var i = 0; i < inputs.length; i++) {
                if (inputs[i].value && inputs[i].value.trim()) {
                    kw = inputs[i].value.trim();
                    break;
                }
            }
            if (kw) {
                window.open(
                    'https://www.amazon.co.jp/s?k='
                    + encodeURIComponent(kw)
                    + '&i=stripbooks',
                    '_blank'
                );
            } else {
                window.parent.document.querySelectorAll(
                    'input[type=text], input[aria-label]'
                )[0].focus();
            }
            return false;
        ">📦 Amazonで本を探す ↗</a>
        """,
        height=54,
    )


def _render_search_results(keyword: str) -> None:
    """検索を実行し、結果カードを表示する。"""
    st.subheader(f"「{keyword}」の検索結果")
    logger.info("検索開始: keyword='%s'", keyword)

    loader = st.empty()
    loader.markdown(
        """
        <div class="loading-container">
            <div class="loading-dots">
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
            </div>
            <div class="loading-message">各サイトを検索中...</div>
            <div class="loading-submessage">図書館・書店の在庫を確認しています</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 全4サイトを並列検索（TTL キャッシュ付き）
    results = check_all_sites(keyword)

    # 全サイトがエラー（ネットワーク断など）の結果は TTL の間残さず、
    # 次回の検索で再試行できるようにする
    all_statuses = [
        results["gifu"],
        results["kani"],
        results["sanseido"],
        results["tsutaya"][0],
    ]
    if all(s == _S_ERROR for s in all_statuses):
        try:
            check_all_sites.clear(keyword)
        except Exception:
            logger.warning("キャッシュクリアに失敗（無視して続行）")

    loader.empty()

    # tsutaya は (BookStatus, url) のタプル
    tsutaya_status, tsutaya_url = results["tsutaya"]
    gifu_status = results["gifu"]
    kani_status = results["kani"]
    sanseido_status = results["sanseido"]

    card_images = _load_card_images_base64()
    logger.info(
        "検索完了: メディコス=%s ミライブ=%s 岐阜駅本屋=%s 各務原BC=%s",
        gifu_status.text,
        kani_status.text,
        sanseido_status.text,
        tsutaya_status.text,
    )

    cards_html = (
        _create_result_card("メディコス", "🏢", gifu_status, build_gifu_url(keyword), card_images["gifu"])
        + _create_result_card("ミライブ", "🌲", kani_status, build_kani_url(keyword), card_images["kani"])
        + _create_result_card("岐阜駅本屋", "📖", sanseido_status, build_sanseido_url(keyword), card_images["sanseido"])
        + _create_result_card("各務原BC", "☕", tsutaya_status, tsutaya_url, card_images["tsutaya"])
    )
    st.markdown(
        f'<div class="results-grid">{cards_html}</div>',
        unsafe_allow_html=True,
    )


# ============================================================================
# メインアプリケーション
# ============================================================================

def main() -> None:
    """Streamlit アプリのエントリーポイント。"""
    _init_session_state()

    # CSS を先頭で注入（キャッシュ済みのため即座に反映）
    bg_base64 = _load_bg_base64()
    st.markdown(_build_app_css(bg_base64), unsafe_allow_html=True)

    # ── ヒーローセクション ────────────────────────────────────────────────
    st.markdown(
        """
        <div class="hero-section">
            <div class="hero-heading">
                <svg class="hero-icon" viewBox="-4 -4 72 72" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="overflow:visible">
                    <defs>
                        <filter id="hero-shadow" x="-30%" y="-30%" width="160%" height="160%">
                            <feDropShadow dx="1" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.3"/>
                        </filter>
                        <filter id="hero-glass" x="-30%" y="-30%" width="160%" height="160%">
                            <feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#000" flood-opacity="0.3"/>
                        </filter>
                    </defs>
                    <g transform="translate(12, 16) scale(0.75)" filter="url(#hero-shadow)">
                        <path d="M 2 15 Q 18 8 32 19 Q 46 8 62 15 L 62 53 Q 46 46 32 57 Q 18 46 2 53 Z" fill="#2563eb" stroke="#1e40af" stroke-width="1.5" stroke-linejoin="round"/>
                        <path d="M 8 50 L 8 53 Q 20 47 32 57 L 32 54 Q 20 44 8 50 Z" fill="#e2e8f0" stroke="#cbd5e1" stroke-width="1" stroke-linejoin="round"/>
                        <path d="M 56 50 L 56 53 Q 44 47 32 57 L 32 54 Q 44 44 56 50 Z" fill="#e2e8f0" stroke="#cbd5e1" stroke-width="1" stroke-linejoin="round"/>
                        <path d="M 8 16 Q 20 10 32 20 L 32 54 Q 20 44 8 50 Z" fill="#fff" stroke="#cbd5e1" stroke-width="1.5" stroke-linejoin="round"/>
                        <path d="M 56 16 Q 44 10 32 20 L 32 54 Q 44 44 56 50 Z" fill="#fff" stroke="#cbd5e1" stroke-width="1.5" stroke-linejoin="round"/>
                        <line x1="32" y1="20" x2="32" y2="54" stroke="#cbd5e1" stroke-width="1.5" stroke-linecap="round"/>
                        <path d="M 32 20 L 35 32 L 32 35 L 29 32 Z" fill="#ef4444" stroke="#b91c1c" stroke-width="1" stroke-linejoin="round"/>
                        <path fill="#fff" stroke="#cbd5e1" stroke-width="1.5" stroke-linejoin="round">
                            <animate attributeName="d" dur="2s" repeatCount="indefinite" keyTimes="0;0.2;0.4;0.6;0.8;1" values="M 32 20 Q 44 10 56 16 L 56 50 Q 44 44 32 54 Z;M 32 20 Q 40 6 46 10 L 46 44 Q 40 38 32 54 Z;M 32 20 Q 32 4 32 6 L 32 40 Q 32 36 32 54 Z;M 32 20 Q 24 6 18 10 L 18 44 Q 24 38 32 54 Z;M 32 20 Q 20 10 8 16 L 8 50 Q 20 44 32 54 Z;M 32 20 Q 44 10 56 16 L 56 50 Q 44 44 32 54 Z"/>
                            <animate attributeName="opacity" dur="2s" repeatCount="indefinite" keyTimes="0;0.8;0.85;0.95;1" values="1;1;0;0;1"/>
                        </path>
                    </g>
                    <g filter="url(#hero-glass)" transform="translate(-10, 42) scale(0.68)">
                        <line x1="14" y1="38" x2="38" y2="14" stroke="#fff" stroke-width="7" stroke-linecap="round"/>
                        <circle cx="42" cy="12" r="8" fill="none" stroke="#fff" stroke-width="5.5"/>
                        <line x1="14" y1="38" x2="38" y2="14" stroke="#1f2937" stroke-width="4" stroke-linecap="round"/>
                        <circle cx="42" cy="12" r="8" fill="#e0f2fe" fill-opacity="0.9" stroke="#1f2937" stroke-width="2.5"/>
                        <path d="M 38 10 A 5 5 0 0 1 41 7" stroke="#fff" stroke-width="2" stroke-linecap="round" fill="none"/>
                    </g>
                </svg>
                <h1 class="hero-title">Book Finder</h1>
            </div>
            <p class="hero-sub">岐阜の本を、ひとまとめに。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── マイページリンク ──────────────────────────────────────────────────
    st.markdown(
        """
        <div class="mypage-links">
            <a href="https://www1.gifu-lib.jp/winj/opac/login.do?lang=ja&dispatch=/opac/mylibrary.do&every=1"
               target="_blank" rel="noopener noreferrer" class="mypage-link">
                🏢 メディコス マイページ
            </a>
            <a href="https://www.kani-lib.jp"
               target="_blank" rel="noopener noreferrer" class="mypage-link">
                🌲 ミライブ マイページ
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 検索エリア ────────────────────────────────────────────────────────
    # 履歴ボタンで選ばれたキーワードを、text_input 生成前に反映する
    pending = st.session_state.pop("pending_keyword", None)
    if pending is not None:
        st.session_state.keyword_input = pending

    st.markdown("### 🔍 キーワード入力")
    keyword_input: str = st.text_input(
        "キーワード",
        placeholder="タイトル・著者名などを入力",
        label_visibility="collapsed",
        key="keyword_input",
    )

    _render_search_history()

    col_search, col_amazon = st.columns(2)

    with col_search:
        should_search = st.button(
            "📚 図書館・書店を検索",
            type="primary",
            use_container_width=True,
        )

    with col_amazon:
        _render_amazon_button()

    st.markdown("---")

    if should_search:
        if not keyword_input:
            st.warning("⚠️ キーワードを入力してください")
        else:
            _add_to_history(keyword_input)
            _render_search_results(keyword_input)

    st.markdown("<br><br>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
