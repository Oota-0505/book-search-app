"""
書籍横断検索アプリ

岐阜市立図書館・可児市立図書館・岐阜駅本屋・草叢BOOKSを一括検索する
Streamlitアプリケーション
"""

import re
import urllib.parse
from typing import Any, Dict, Optional, Tuple
import requests
import streamlit as st
from bs4 import BeautifulSoup

# ============================================================================
# 設定・定数
# ============================================================================

# Page Config
st.set_page_config(page_title="本検索アプリ", layout="wide", page_icon="📚")

# HTTP設定
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT_SHORT = 10
TIMEOUT_MEDIUM = 15

# アプリ設定
HISTORY_LIMIT = 5
KUSA_BOOKS_KEYWORD = "各務原店"

# 外部API（書誌情報）
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"

# 型定義
Status = Dict[str, str]

# ============================================================================
# CSSスタイル
# ============================================================================

APP_CSS = """
<style>
    :root {
        --bg0: #F7FAFF;
        --bg1: #FFFFFF;
        --text: #0F172A;
        --muted: #64748B;
        --border: rgba(15, 23, 42, 0.10);
        --shadow: 0 10px 25px rgba(2, 6, 23, 0.06);
        --shadow-hover: 0 14px 32px rgba(2, 6, 23, 0.10);
        --blue0: #3B82F6;
        --blue1: #2563EB;
        --ok: #10B981;
        --ng: #EF4444;
        --warn: #F59E0B;
        --amber0: #FF9900;
        --amber1: #FF6A00;
        --green0: #10B981;
        --green1: #059669;
    }

    /* App background & typography */
    .stApp {
        background: radial-gradient(1200px 600px at 10% 0%, rgba(59,130,246,0.10), transparent 55%),
                    radial-gradient(900px 450px at 90% 0%, rgba(255,153,0,0.10), transparent 55%),
                    linear-gradient(180deg, var(--bg0), var(--bg1));
        color: var(--text);
    }
    .block-container {
        max-width: 1120px;
        padding-top: 2.25rem;
        padding-bottom: 2.5rem;
    }
    h1 {
        color: #1E3A8A;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
        letter-spacing: -0.02em;
    }

    /* Text input */
    div[data-testid="stTextInput"] input {
        border-radius: 12px !important;
        border: 1px solid var(--border) !important;
        padding: 0.85rem 0.95rem !important;
        box-shadow: 0 1px 0 rgba(2,6,23,0.02) !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: rgba(37,99,235,0.55) !important;
        box-shadow: 0 0 0 4px rgba(37,99,235,0.18) !important;
    }

    /* Buttons: primary vs secondary */
    button[data-testid="stBaseButton-primary"] {
        width: 100%;
        background: linear-gradient(90deg, #4F46E5 0%, #3B82F6 100%) !important;
        color: white !important;
        font-weight: 800 !important;
        border: none !important;
        padding: 0.70rem 1rem !important;
        border-radius: 12px !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
        box-shadow: 0 10px 18px rgba(59, 130, 246, 0.22) !important;
        min-height: 48px !important;
    }
    button[data-testid="stBaseButton-primary"]:hover {
        background: linear-gradient(90deg, #4338CA 0%, #2563EB 100%) !important;
        transform: translateY(-1px);
        box-shadow: 0 14px 24px rgba(59, 130, 246, 0.28) !important;
    }

    /* History buttons (secondary) */
    button[data-testid="stBaseButton-secondary"] {
        width: 100%;
        border-radius: 999px !important;
        border: 1px solid var(--border) !important;
        background: rgba(255,255,255,0.85) !important;
        color: var(--text) !important;
        font-weight: 700 !important;
        padding: 0.45rem 0.65rem !important;
        box-shadow: 0 4px 10px rgba(2,6,23,0.04) !important;
    }
    button[data-testid="stBaseButton-secondary"]:hover {
        border-color: rgba(37,99,235,0.35) !important;
        box-shadow: 0 10px 18px rgba(2,6,23,0.06) !important;
        transform: translateY(-1px);
    }

    /* Result card */
    .result-card {
        background: rgba(255,255,255,0.92);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 16px 16px 14px 16px;
        margin: 10px 0;
        box-shadow: var(--shadow);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
        position: relative;
        overflow: hidden;
    }
    .result-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-hover);
    }
    .border-ok { border-left: 5px solid var(--ok) !important; }
    .border-ng { border-left: 5px solid var(--ng) !important; }
    .border-warn { border-left: 5px solid var(--warn) !important; }

    .card-top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
    }
    .site {
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: 0;
    }
    .site-icon {
        width: 38px;
        height: 38px;
        border-radius: 12px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: rgba(37,99,235,0.10);
        border: 1px solid rgba(37,99,235,0.16);
        flex: 0 0 auto;
        font-size: 18px;
    }
    .site-title {
        font-size: 1.02rem;
        font-weight: 800;
        color: var(--text);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        letter-spacing: -0.01em;
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 0.95rem;
        font-weight: 800;
        border: 1px solid var(--border);
        background: rgba(255,255,255,0.75);
        flex: 0 0 auto;
    }
    .pill-ok { border-color: rgba(16,185,129,0.35); background: rgba(16,185,129,0.10); }
    .pill-ng { border-color: rgba(239,68,68,0.35); background: rgba(239,68,68,0.08); }
    .pill-warn { border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.12); }

    /* Link buttons */
    .btn-link {
        display: flex !important;
        width: 100%;
        text-align: center;
        color: white !important;
        text-decoration: none;
        border-radius: 12px;
        font-weight: 800;
        padding: 0.70rem 1rem !important;
        min-height: 48px !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 10px 18px rgba(2,6,23,0.10);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        line-height: 1.4;
        background: linear-gradient(135deg, var(--blue0) 0%, var(--blue1) 100%);
    }
    .btn-link:hover {
        transform: translateY(-1px);
        box-shadow: 0 14px 24px rgba(2,6,23,0.14);
        filter: brightness(1.02);
    }
    
    /* Amazon button - separate styling */
    a.btn-amazon {
        display: flex !important;
        width: 100% !important;
        text-align: center !important;
        color: white !important;
        text-decoration: none !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        padding: 0.70rem 1rem !important;
        min-height: 48px !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 10px 18px rgba(16, 185, 129, 0.22) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
        line-height: 1.4 !important;
        background: linear-gradient(135deg, var(--green0) 0%, var(--green1) 100%) !important;
        border: none !important;
        margin: 0 !important;
    }
    a.btn-amazon:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 14px 24px rgba(16, 185, 129, 0.28) !important;
        filter: brightness(1.02) !important;
        color: white !important;
    }

    /* Alert/Info styling */
    div[data-testid="stAlertContainer"] {
        border-radius: 12px !important;
        border: 1px solid rgba(16, 185, 129, 0.2) !important;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.08) 100%) !important;
        padding: 1rem !important;
        box-shadow: 0 4px 10px rgba(16, 185, 129, 0.08) !important;
        font-weight: 600 !important;
        color: var(--text) !important;
        margin: 0 !important;
        width: 100% !important;
    }

    /* Loading (stylish bounce dots) */
    .loading-container {
        width: 100%;
        padding: 40px 20px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 20px;
        margin: 20px 0;
    }
    .loading-dots {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
    }
    .loading-dot {
        width: 16px;
        height: 16px;
        border-radius: 50%;
        animation: bounce 1.4s ease-in-out infinite;
    }
    .loading-dot:nth-child(1) {
        background: linear-gradient(135deg, #4F46E5 0%, #3B82F6 100%);
        animation-delay: 0s;
    }
    .loading-dot:nth-child(2) {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        animation-delay: 0.2s;
    }
    .loading-dot:nth-child(3) {
        background: linear-gradient(135deg, #F59E0B 0%, #D97706 100%);
        animation-delay: 0.4s;
    }
    @keyframes bounce {
        0%, 80%, 100% {
            transform: scale(0.6);
            opacity: 0.5;
        }
        40% {
            transform: scale(1.2);
            opacity: 1;
        }
    }
    .loading-message {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--text);
        text-align: center;
        letter-spacing: -0.01em;
    }
    .loading-submessage {
        font-size: 0.9rem;
        color: var(--muted);
        text-align: center;
    }
    @media (prefers-reduced-motion: reduce) {
        .loading-dot { animation: none; opacity: 1; transform: scale(1); }
    }

    /* Summary card (Book Info) */
    .summary-card {
        background: rgba(255,255,255,0.95);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 24px;
        margin: 20px 0;
        box-shadow: var(--shadow);
    }
    .summary-title {
        font-size: 1.4rem;
        font-weight: 800;
        color: #1E3A8A;
        margin-bottom: 4px;
        line-height: 1.3;
    }
    .summary-meta {
        font-size: 0.95rem;
        color: var(--muted);
        margin-bottom: 16px;
        font-weight: 500;
    }
    .summary-text {
        font-size: 1.05rem;
        line-height: 1.7;
        color: var(--text);
        margin-top: 12px;
    }
    .summary-img {
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        max-width: 100%;
        height: auto;
    }

    /* Small screens tweaks */
    @media (max-width: 640px) {
        .block-container { padding-top: 1.4rem; }
        .site-title { font-size: 0.98rem; }
        .status-pill { font-size: 0.92rem; }
    }
</style>
"""


# ============================================================================
# ユーティリティ関数
# ============================================================================

def make_status(text: str, css_class: str, icon: str) -> Status:
    """
    ステータス情報を生成する
    
    Args:
        text: ステータステキスト
        css_class: CSSクラス名
        icon: アイコン文字列
    
    Returns:
        ステータス辞書
    """
    return {"text": text, "class": css_class, "icon": icon}


def init_session_state() -> None:
    """セッションステートを初期化"""
    if "search_history" not in st.session_state:
        st.session_state.search_history = []


def add_to_history(keyword: str) -> None:
    """
    検索履歴に追加（最大5件）
    
    Args:
        keyword: 検索キーワード
    """
    if not keyword:
        return
    if keyword in st.session_state.search_history:
        st.session_state.search_history.remove(keyword)
    st.session_state.search_history.insert(0, keyword)
    if len(st.session_state.search_history) > HISTORY_LIMIT:
        st.session_state.search_history = st.session_state.search_history[:HISTORY_LIMIT]


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def fetch_book_info_google_books(keyword: str) -> Optional[Dict[str, Any]]:
    """
    Google Books APIからキーワードに最も近い1冊の書誌情報を取得する（無料枠あり）
    """
    try:
        params = {
            "q": keyword,
            "maxResults": 1,
            "printType": "books",
            "langRestrict": "ja",
        }
        res = requests.get(
            GOOGLE_BOOKS_API_URL,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT_MEDIUM,
        )
        res.raise_for_status()
        data = res.json()
        items = data.get("items") or []
        if not items:
            return None

        volume_info = (items[0] or {}).get("volumeInfo") or {}
        identifiers = volume_info.get("industryIdentifiers") or []
        isbn_13 = None
        isbn_10 = None
        for it in identifiers:
            if (it or {}).get("type") == "ISBN_13":
                isbn_13 = (it or {}).get("identifier")
            if (it or {}).get("type") == "ISBN_10":
                isbn_10 = (it or {}).get("identifier")

        image_links = volume_info.get("imageLinks") or {}
        return {
            "title": volume_info.get("title"),
            "subtitle": volume_info.get("subtitle"),
            "authors": volume_info.get("authors") or [],
            "publisher": volume_info.get("publisher"),
            "publishedDate": volume_info.get("publishedDate"),
            "description": volume_info.get("description"),
            "categories": volume_info.get("categories") or [],
            "pageCount": volume_info.get("pageCount"),
            "language": volume_info.get("language"),
            "thumbnail": image_links.get("thumbnail") or image_links.get("smallThumbnail"),
            "infoLink": volume_info.get("infoLink"),
            "isbn13": isbn_13,
            "isbn10": isbn_10,
        }
    except Exception:
        return None


def render_book_summary_section(keyword: str) -> None:
    """
    検索結果の下に、本の概要（Google Booksから取得した説明文を5行程度で表示）を表示する
    """
    book = fetch_book_info_google_books(keyword)
    if not book:
        return

    description = book.get("description")
    if not description or description == "不明":
        return

    title = book.get("title") or keyword
    subtitle = book.get("subtitle")
    authors_list = book.get("authors") or []
    authors = " / ".join(authors_list) if authors_list else "不明"
    published_date = book.get("publishedDate") or "不明"
    isbn = book.get("isbn13") or book.get("isbn10") or "不明"
    info_link = book.get("infoLink")
    thumb = book.get("thumbnail")

    # 説明文を5行程度（最初の5文または300文字程度）に簡略化
    sentences = description.split('。')
    # 空文字列を除く
    sentences = [s.strip() for s in sentences if s.strip()]
    
    summary = ""
    if not sentences:
        # 文区切りができない場合は単純カット
        summary = description[:300].rstrip('。') + '...'
    else:
        # 最初の5文までを結合（最大300文字程度）
        summary_parts = []
        total_length = 0
        for i, sentence in enumerate(sentences[:5]):
            if total_length + len(sentence) > 300:
                break
            summary_parts.append(sentence)
            total_length += len(sentence) + 1
        
        if not summary_parts:
            summary = description[:300].rstrip('。') + '...'
        else:
            summary = '。'.join(summary_parts)
            if not summary.endswith('。'):
                summary += '。'
            if len(sentences) > len(summary_parts):
                summary += '...'

    st.markdown("---")
    
    # HTMLでリッチなデザインを生成
    # 画像がある場合とない場合でレイアウト調整
    
    img_html = ""
    if thumb:
        # 高解像度版があれば置換（zoom=1 -> zoom=0など）するテクニックもあるが、
        # ここでは標準のサムネイルを使用し、CSSで影などをつける
        img_html = f'<img src="{thumb}" class="summary-img" alt="{title}">'
    else:
        # 画像なしの場合はプレースホルダーアイコン
        img_html = '<div style="font-size:4rem; text-align:center;">📚</div>'

    subtitle_html = f'<div style="color: #64748B; font-weight: 700; margin-bottom: 4px;">{subtitle}</div>' if subtitle else ""
    
    html_content = f"""
    <div class="summary-card">
        <div style="display: flex; gap: 24px; flex-wrap: wrap;">
            <div style="flex: 0 0 140px; min-width: 140px; display: flex; justify-content: center; align-items: flex-start;">
                {img_html}
            </div>
            <div style="flex: 1; min-width: 200px;">
                <div class="summary-title">{title}</div>
                {subtitle_html}
                <div class="summary-meta">
                    著者: {authors} | 出版: {published_date}<br>
                    ISBN: {isbn}
                </div>
                <div style="border-top: 2px solid #F1F5F9; margin: 12px 0;"></div>
                <div class="summary-text">
                    {summary}
                </div>
                <div style="margin-top: 16px; text-align: right;">
                    <a href="{info_link}" target="_blank" style="color: #3B82F6; font-weight: 700; text-decoration: none;">Google Booksで詳細を見る ↗</a>
                </div>
            </div>
        </div>
    </div>
    """
    
    st.markdown(html_content, unsafe_allow_html=True)

# ============================================================================
# 各サイトの在庫チェック関数
# ============================================================================

def check_gifu_lib(keyword: str) -> Status:
    """
    岐阜市立図書館の在庫チェック
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        ステータス情報
    """
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # セッション初期化
        session.get(
            "https://www1.gifu-lib.jp/winj/opac/top.do",
            timeout=TIMEOUT_SHORT
        )
        
        # 検索実行
        search_url = "https://www1.gifu-lib.jp/winj/opac/search-standard.do"
        params = {
            "txt_word": keyword,
            "hid_word_column": "fulltext",
            "submit_btn_searchEasy": "search"
        }
        res = session.get(
            search_url,
            params=params,
            timeout=TIMEOUT_SHORT,
            allow_redirects=True
        )
        res.encoding = res.apparent_encoding
        
        # 判定（0件表現が複数あるため両方見る）
        nohit_phrases = (
            "該当する資料はありません",
            "該当するリストが存在しません",
        )
        if "g-mediacosmos.jp" in res.url or any(p in res.text for p in nohit_phrases):
            return make_status("なし", "border-ng", "❌")
        
        soup = BeautifulSoup(res.text, 'html.parser')
        page_title = soup.title.string if soup.title else ""
        if "検索結果" in page_title or "資料検索" in page_title:
            return make_status("あり", "border-ok", "⭕️")
        return make_status("あり", "border-ok", "⭕️")
    except Exception:
        return make_status("エラー", "border-warn", "⚠️")


def check_kani_lib(keyword: str) -> Status:
    """
    可児市立図書館の在庫チェック
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        ステータス情報
    """
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # セッション初期化
        session.get(
            "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCH1.CSP?DB=LIB&MODE=1",
            timeout=TIMEOUT_SHORT
        )
        
        # 検索実行
        url = "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP"
        params = {
            "text(1)": keyword,
            "opr(1)": "OR",
            "DB": "LIB",
            "PID": "OPWSRCH1",
            "FLG": "SEARCH",
            "MODE": "1",
            "SORT": "-3",
            "qual(1)": "MZALL"
        }
        res = session.get(url, params=params, timeout=TIMEOUT_MEDIUM)
        res.encoding = res.apparent_encoding
        
        # 判定
        if "該当する資料はありません" in res.text or "検索結果 0件" in res.text:
            return make_status("なし", "border-ng", "❌")
        elif "○ 在架あり" in res.text:
            return make_status("在庫あり", "border-ok", "⭕️")
        elif "貸出中" in res.text or "予約" in res.text:
            return make_status("貸出中", "border-warn", "⚠️")
        return make_status("あり", "border-ok", "⭕️")
    except Exception:
        return make_status("エラー", "border-warn", "⚠️")


def check_sanseido(keyword: str) -> Status:
    """
    岐阜駅本屋の在庫チェック
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        ステータス情報
    """
    try:
        url = "https://www.books-sanseido.jp/booksearch/BookSearchExec.action"
        params = {
            "shopCode": "0458",
            "keyword": keyword,
            "defaultShopCode": "",
            "title": "",
            "author": "",
            "isbn": "",
            "genreCode": "",
            "search": "検索"
        }
        res = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT_SHORT)
        res.encoding = res.apparent_encoding

        # 0件判定（表記ゆれ）
        if "検索結果：0件" in res.text or "検索結果:0件" in res.text:
            return make_status("なし", "border-ng", "❌")

        # 件数（例: "<strong>1</strong>件中"）
        match = re.search(r'<strong>\s*(\d+)\s*</strong>\s*件中', res.text)
        total = int(match.group(1)) if match else None
        if total == 0:
            return make_status("なし", "border-ng", "❌")

        # 在庫（例: "在庫： ×" / "在庫： ○"）
        stock_marks = re.findall(r'在庫：\s*([○×△▲])', res.text)
        if stock_marks:
            if any(mark != "×" for mark in stock_marks):
                return make_status("在庫あり", "border-ok", "⭕️")
            return make_status("なし", "border-ng", "❌")

        # フォールバック：ヒットはあるが在庫表現が取れない（要確認）
        if total is not None and total > 0:
            return make_status(f"{total}件", "border-warn", "⚠️")
        return make_status("判定保留", "border-warn", "⚠️")
    except Exception:
        return make_status("エラー", "border-warn", "⚠️")


def _extract_first_tsutaya_work_id(html: str) -> Optional[str]:
    """
    草叢BOOKSキーワード検索結果HTMLから1位のworkIdを抽出（販売リンク）
    
    Args:
        html: HTML文字列
    
    Returns:
        workId文字列、見つからない場合はNone
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        anchor = soup.find("a", href=re.compile(r"/search/result/select\?"))
        if not anchor or not anchor.get("href"):
            return None
        match = re.search(r"workId=(\d+)", anchor["href"])
        return match.group(1) if match else None
    except Exception:
        return None


def _extract_tsutaya_product_key_from_select(work_id: str) -> Optional[str]:
    """
    草叢BOOKSのselectページを開き、productKey(ISBN/JAN)を抽出
    
    Args:
        work_id: 作品ID
    
    Returns:
        productKey文字列、見つからない場合はNone
    """
    try:
        select_url = "https://store-tsutaya.tsite.jp/search/result/select"
        params = {
            "saleType": "sell",
            "workId": work_id,
            "itemType": "book"
        }
        res = requests.get(
            select_url,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT_MEDIUM,
            allow_redirects=True
        )
        # ページ内に在庫リンクがある（例: /search/result/stock?...&productKey=978...）
        match = re.search(r"productKey=(\d+)", res.text)
        if match:
            return match.group(1)
        # リダイレクトURL末尾にISBNが入るケース（.../43575108/978...）
        match2 = re.search(r"/\d+/(\d{10,13})\b", res.url)
        return match2.group(1) if match2 else None
    except Exception:
        return None


def build_tsutaya_urls(
    keyword: str,
    store_keyword: str = KUSA_BOOKS_KEYWORD
) -> Dict[str, Optional[str]]:
    """
    草叢BOOKSの検索URLと在庫URLを生成
    
    Args:
        keyword: 検索キーワード
        store_keyword: 店舗検索キーワード（デフォルト: "各務原"）
    
    Returns:
        検索URL、在庫URL、work_id、product_keyを含む辞書
    """
    search_url = (
        f"https://store-tsutaya.tsite.jp/search/result/"
        f"?keyword={urllib.parse.quote(keyword)}&itemType=book&limit=20"
    )
    try:
        res = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT_MEDIUM)
        work_id = _extract_first_tsutaya_work_id(res.text)
        if not work_id:
            return {
                "search_url": search_url,
                "stock_url": search_url,
                "work_id": None,
                "product_key": None
            }
        
        product_key = _extract_tsutaya_product_key_from_select(work_id)
        if not product_key:
            return {
                "search_url": search_url,
                "stock_url": search_url,
                "work_id": work_id,
                "product_key": None
            }
        
        stock_url = (
            "https://store-tsutaya.tsite.jp/search/result/stock/result"
            f"?workId={work_id}&saleType=sell&itemType=book&productKey={product_key}"
            f"&storeSearchKeyword={urllib.parse.quote(store_keyword)}"
        )
        return {
            "search_url": search_url,
            "stock_url": stock_url,
            "work_id": work_id,
            "product_key": product_key
        }
    except Exception:
        return {
            "search_url": search_url,
            "stock_url": search_url,
            "work_id": None,
            "product_key": None
        }


def check_tsutaya(
    keyword: str,
    store_keyword: str = KUSA_BOOKS_KEYWORD
) -> Tuple[Status, str]:
    """
    草叢BOOKSの在庫チェック（1位の候補を採用）
    
    Args:
        keyword: 検索キーワード
        store_keyword: 店舗検索キーワード（デフォルト: "各務原"）
    
    Returns:
        (ステータス情報, URL)のタプル
    """
    try:
        urls = build_tsutaya_urls(keyword, store_keyword=store_keyword)
        # そもそも候補が取れない＝判定不可（リンクは検索ページへ）
        if not urls.get("work_id") or not urls.get("product_key"):
            return (
                make_status("判定保留", "border-warn", "⚠️"),
                urls["stock_url"]
            )

        res = requests.get(urls["stock_url"], headers=HEADERS, timeout=TIMEOUT_MEDIUM)
        res.encoding = res.apparent_encoding
        if "在庫あり" in res.text:
            return make_status("在庫あり", "border-ok", "⭕️"), urls["stock_url"]
        if "在庫なし" in res.text or "入荷予定は店舗にお問い合わせ下さい" in res.text:
            return make_status("なし", "border-ng", "❌"), urls["stock_url"]
        return make_status("判定保留", "border-warn", "⚠️"), urls["stock_url"]
    except Exception:
        return (
            make_status("エラー", "border-warn", "⚠️"),
            "https://store-tsutaya.tsite.jp/search/?sheader_item-search"
        )


def check_status(keyword: str) -> Dict[str, Status]:
    """
    全サイトの在庫状況をチェック
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        各サイトのステータス情報を含む辞書
    """
    return {
        'gifu': check_gifu_lib(keyword),
        'kani': check_kani_lib(keyword),
        'sanseido': check_sanseido(keyword),
    }


# ============================================================================
# UI生成関数
# ============================================================================

def create_result_card(site_name: str, icon: str, status: Status, url: str) -> str:
    """
    検索結果カードのHTMLを生成
    
    Args:
        site_name: サイト名
        icon: アイコン文字列
        status: ステータス情報
        url: リンクURL
    
    Returns:
        HTML文字列
    """
    pill_class_map = {
        "border-ok": "pill-ok",
        "border-ng": "pill-ng",
        "border-warn": "pill-warn",
    }
    pill_class = pill_class_map.get(status.get("class", ""), "pill-warn")
    return f"""
    <div class="result-card {status['class']}">
        <div class="card-top">
            <div class="site">
                <span class="site-icon">{icon}</span>
                <span class="site-title">{site_name}</span>
            </div>
            <div class="status-pill {pill_class}">{status['icon']} {status['text']}</div>
        </div>
        <a href="{url}" target="_blank" rel="noopener noreferrer" class="btn-link">結果を開く ↗</a>
    </div>
    """


def build_gifu_url(keyword: str) -> str:
    """
    岐阜市立図書館の検索URLを生成
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        URL文字列
    """
    params = {
        "lang": "ja",
        "txt_word": keyword,
        "hid_word_column": "fulltext",
        "submit_btn_searchEasy": "search"
    }
    base_url = "https://www1.gifu-lib.jp/winj/opac/search-standard.do"
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def build_kani_url(keyword: str) -> str:
    """
    可児市立図書館の検索URLを生成
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        URL文字列
    """
    params = {
        "opr(1)": "OR",
        "DB": "LIB",
        "PID": "OPWSRCH1",
        "FLG": "SEARCH",
        "MODE": "1",
        "SORT": "-3",
        "qual(1)": "MZALL",
        "text(1)": keyword
    }
    base_url = "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP"
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def build_sanseido_url(keyword: str) -> str:
    """
    岐阜駅本屋の検索URLを生成
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        URL文字列
    """
    params = {
        "shopCode": "0458",
        "keyword": keyword,
        "defaultShopCode": "",
        "title": "",
        "author": "",
        "isbn": "",
        "genreCode": "",
        "search": "検索",
    }
    base_url = "https://www.books-sanseido.jp/booksearch/BookSearchExec.action"
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def build_amazon_url(keyword: str) -> str:
    """
    Amazonの検索URLを生成
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        URL文字列
    """
    return f"https://www.amazon.co.jp/s?k={urllib.parse.quote(keyword)}"


# ============================================================================
# メインアプリケーション
# ============================================================================

def render_search_history() -> None:
    """検索履歴を表示"""
    if not st.session_state.search_history:
        return
    
    st.caption("🕒 検索履歴:")
    cols = st.columns(HISTORY_LIMIT)
    for i, hist_kw in enumerate(st.session_state.search_history[:HISTORY_LIMIT]):
        if cols[i].button(hist_kw, key=f"h_{i}", use_container_width=True):
            st.session_state.keyword_input = hist_kw
            st.rerun()


def render_search_results(keyword: str) -> None:
    """
    検索結果を表示
    
    Args:
        keyword: 検索キーワード
    """
    st.subheader(f"「{keyword}」の検索結果")

    # カスタムローダーを表示
    loader_placeholder = st.empty()
    loader_placeholder.markdown(
        """
        <div class="loading-container">
            <div class="loading-dots">
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
                <div class="loading-dot"></div>
            </div>
            <div class="loading-message">📚 各サイトを検索中...</div>
            <div class="loading-submessage">図書館・書店の在庫を確認しています</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # 検索実行
    status = check_status(keyword)
    tsutaya_status, tsutaya_url = check_tsutaya(keyword, store_keyword=KUSA_BOOKS_KEYWORD)
    
    # ローダーを消す
    loader_placeholder.empty()

    # 2x2 レイアウト（スマホでも見やすい）
    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)

    with r1c1:
        gifu_url = build_gifu_url(keyword)
        st.markdown(
            create_result_card("岐阜市立図書館", "🏢", status["gifu"], gifu_url),
            unsafe_allow_html=True
        )

    with r1c2:
        kani_url = build_kani_url(keyword)
        st.markdown(
            create_result_card("可児市立図書館", "🌲", status["kani"], kani_url),
            unsafe_allow_html=True
        )

    with r2c1:
        sanseido_url = build_sanseido_url(keyword)
        st.markdown(
            create_result_card("岐阜駅本屋", "📖", status["sanseido"], sanseido_url),
            unsafe_allow_html=True
        )

    with r2c2:
        st.markdown(
            create_result_card(
                "草叢BOOKS",
                "☕",
                tsutaya_status,
                tsutaya_url
            ),
            unsafe_allow_html=True,
        )

    # 検索結果の下に本の概要を表示
    render_book_summary_section(keyword)


def main() -> None:
    """メインアプリケーション"""
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.title("📚 Book Finder")
    st.caption("岐阜市図書館・可児市図書館・岐阜駅本屋・草叢BOOKSを一括検索")

    init_session_state()

    st.markdown("### 🔍 キーワード入力")
    keyword_input = st.text_input(
        "キーワード",
        placeholder="キーワードを入力",
        label_visibility="collapsed",
        key="keyword_input",
    )

    # 検索履歴表示
    render_search_history()

    # アクションエリア
    col_search, col_amazon = st.columns([1, 1])

    with col_amazon:
        # キーワードがない場合は空文字列で検索（またはトップページ）
        search_keyword = keyword_input if keyword_input else ""
        amazon_url = build_amazon_url(search_keyword) if search_keyword else "https://www.amazon.co.jp/s?k="
        st.markdown(
            f"""
            <a href="{amazon_url}" target="_blank" rel="noopener noreferrer" class="btn-amazon">
                📦 Amazonで本を探す ↗
            </a>
            """,
            unsafe_allow_html=True,
        )

    with col_search:
        should_search = st.button(
            "📚 図書館・書店を検索",
            type="primary",
            use_container_width=True
        )

    st.markdown("---")

    if should_search:
        if not keyword_input:
            st.warning("⚠️ キーワードを入力してください")
        else:
            add_to_history(keyword_input)
            render_search_results(keyword_input)

    st.markdown("<br><br>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
