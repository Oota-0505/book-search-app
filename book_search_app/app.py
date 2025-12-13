import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
from typing import Optional, Dict, Tuple

# Page Config
st.set_page_config(page_title="本・図書館 横断検索", layout="wide", page_icon="📚")

# Constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HISTORY_LIMIT = 5
TSUTAYA_STORE_KEYWORD = "各務原"

# --- Custom CSS for Modern UI ---
st.markdown("""
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
    .btn-link, .btn-amazon {
        display: block;
        width: 100%;
        text-align: center;
        color: white !important;
        text-decoration: none;
        border-radius: 12px;
        font-weight: 800;
        padding: 11px 0;
        box-shadow: 0 10px 18px rgba(2,6,23,0.10);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        line-height: 1.4;
    }
    .btn-link {
        background: linear-gradient(135deg, var(--blue0) 0%, var(--blue1) 100%);
    }
    .btn-amazon {
        background: linear-gradient(135deg, var(--amber0) 0%, var(--amber1) 100%);
    }
    .btn-link:hover, .btn-amazon:hover {
        transform: translateY(-1px);
        box-shadow: 0 14px 24px rgba(2,6,23,0.14);
        filter: brightness(1.02);
    }

    /* Small screens tweaks */
    @media (max-width: 640px) {
        .block-container { padding-top: 1.4rem; }
        .site-title { font-size: 0.98rem; }
        .status-pill { font-size: 0.92rem; }
    }
</style>
""", unsafe_allow_html=True)

st.title("📚 Book Finder")
st.caption("岐阜市図書館・可児市図書館・三省堂（岐阜）・TSUTAYA（各務原）を一括検索")

# Initialize History
if 'search_history' not in st.session_state:
    st.session_state.search_history = []

def add_to_history(kw):
    """検索履歴に追加（最大5件）"""
    if not kw:
        return
    if kw in st.session_state.search_history:
        st.session_state.search_history.remove(kw)
    st.session_state.search_history.insert(0, kw)
    if len(st.session_state.search_history) > HISTORY_LIMIT:
        st.session_state.search_history = st.session_state.search_history[:HISTORY_LIMIT]

def check_gifu_lib(keyword):
    """岐阜市立図書館の在庫チェック"""
    try:
        session = requests.Session()
        headers = {"User-Agent": USER_AGENT}
        
        # セッション初期化
        session.get("https://www1.gifu-lib.jp/winj/opac/top.do", headers=headers, timeout=10)
        
        # 検索実行
        search_url = "https://www1.gifu-lib.jp/winj/opac/search-standard.do"
        params = {"txt_word": keyword, "hid_word_column": "fulltext", "submit_btn_searchEasy": "search"}
        res = session.get(search_url, params=params, headers=headers, timeout=10, allow_redirects=True)
        res.encoding = res.apparent_encoding
        
        # 判定（0件表現が複数あるため両方見る）
        nohit_phrases = (
            "該当する資料はありません",
            "該当するリストが存在しません",
        )
        if "g-mediacosmos.jp" in res.url or any(p in res.text for p in nohit_phrases):
            return {"text": "なし", "class": "border-ng", "icon": "❌"}
        else:
            soup = BeautifulSoup(res.text, 'html.parser')
            page_title = soup.title.string if soup.title else ""
            if "検索結果" in page_title or "資料検索" in page_title:
                return {"text": "あり", "class": "border-ok", "icon": "⭕️"}
            return {"text": "あり", "class": "border-ok", "icon": "⭕️"}
    except Exception:
        return {"text": "エラー", "class": "border-warn", "icon": "⚠️"}

def check_kani_lib(keyword):
    """可児市立図書館の在庫チェック"""
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        
        # セッション初期化
        session.get("https://www.kani-lib.jp/csp/opw/OPW/OPWSRCH1.CSP?DB=LIB&MODE=1", timeout=10)
        
        # 検索実行
        url = "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP"
        params = {
            "text(1)": keyword, "opr(1)": "OR", "DB": "LIB", "PID": "OPWSRCH1",
            "FLG": "SEARCH", "MODE": "1", "SORT": "-3", "qual(1)": "MZALL"
        }
        res = session.get(url, params=params, timeout=15)
        res.encoding = res.apparent_encoding
        
        # 判定
        if "該当する資料はありません" in res.text or "検索結果 0件" in res.text:
            return {"text": "なし", "class": "border-ng", "icon": "❌"}
        elif "○ 在架あり" in res.text:
            return {"text": "在庫あり", "class": "border-ok", "icon": "⭕️"}
        elif "貸出中" in res.text or "予約" in res.text:
            return {"text": "貸出中", "class": "border-warn", "icon": "⚠️"}
        return {"text": "あり", "class": "border-ok", "icon": "⭕️"}
    except Exception:
        return {"text": "エラー", "class": "border-warn", "icon": "⚠️"}

def check_sanseido(keyword):
    """三省堂岐阜の在庫チェック"""
    try:
        url = "https://www.books-sanseido.jp/booksearch/BookSearchExec.action"
        params = {
            "shopCode": "0458", "keyword": keyword, "defaultShopCode": "",
            "title": "", "author": "", "isbn": "", "genreCode": "", "search": "検索"
        }
        headers = {"User-Agent": USER_AGENT}
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.encoding = res.apparent_encoding

        # 0件判定（表記ゆれ）
        if "検索結果：0件" in res.text or "検索結果:0件" in res.text:
            return {"text": "なし", "class": "border-ng", "icon": "❌"}

        # 件数（例: "<strong>1</strong>件中"）
        m = re.search(r'<strong>\s*(\d+)\s*</strong>\s*件中', res.text)
        total = int(m.group(1)) if m else None
        if total == 0:
            return {"text": "なし", "class": "border-ng", "icon": "❌"}

        # 在庫（例: "在庫： ×" / "在庫： ○"）
        stock_marks = re.findall(r'在庫：\s*([○×△▲])', res.text)
        if stock_marks:
            if any(mark != "×" for mark in stock_marks):
                return {"text": "在庫あり", "class": "border-ok", "icon": "⭕️"}
            return {"text": "なし", "class": "border-ng", "icon": "❌"}

        # フォールバック：ヒットはあるが在庫表現が取れない（要確認）
        if total is not None and total > 0:
            return {"text": f"{total}件", "class": "border-warn", "icon": "⚠️"}
        return {"text": "判定保留", "class": "border-warn", "icon": "⚠️"}
    except Exception:
        return {"text": "エラー", "class": "border-warn", "icon": "⚠️"}

def _extract_first_tsutaya_work_id(html: str) -> Optional[str]:
    """TSUTAYAキーワード検索結果HTMLから1位のworkIdを抽出（販売リンク）"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        a = soup.find("a", href=re.compile(r"/search/result/select\?"))
        if not a or not a.get("href"):
            return None
        m = re.search(r"workId=(\d+)", a["href"])
        return m.group(1) if m else None
    except Exception:
        return None

def _extract_tsutaya_product_key_from_select(work_id: str) -> Optional[str]:
    """TSUTAYAのselectページを開き、productKey(ISBN/JAN)を抽出"""
    try:
        select_url = "https://store-tsutaya.tsite.jp/search/result/select"
        params = {"saleType": "sell", "workId": work_id, "itemType": "book"}
        res = requests.get(select_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15, allow_redirects=True)
        # ページ内に在庫リンクがある（例: /search/result/stock?...&productKey=978...）
        m = re.search(r"productKey=(\d+)", res.text)
        if m:
            return m.group(1)
        # リダイレクトURL末尾にISBNが入るケース（.../43575108/978...）
        m2 = re.search(r"/\d+/(\d{10,13})\b", res.url)
        return m2.group(1) if m2 else None
    except Exception:
        return None

def build_tsutaya_urls(keyword: str, store_keyword: str = TSUTAYA_STORE_KEYWORD) -> Dict[str, Optional[str]]:
    """TSUTAYAの検索URLと（可能なら）各務原在庫URLを生成"""
    search_url = f"https://store-tsutaya.tsite.jp/search/result/?keyword={urllib.parse.quote(keyword)}&itemType=book&limit=20"
    try:
        res = requests.get(search_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        work_id = _extract_first_tsutaya_work_id(res.text)
        if not work_id:
            return {"search_url": search_url, "stock_url": search_url, "work_id": None, "product_key": None}
        product_key = _extract_tsutaya_product_key_from_select(work_id)
        if not product_key:
            return {"search_url": search_url, "stock_url": search_url, "work_id": work_id, "product_key": None}
        stock_url = (
            "https://store-tsutaya.tsite.jp/search/result/stock/result"
            f"?workId={work_id}&saleType=sell&itemType=book&productKey={product_key}"
            f"&storeSearchKeyword={urllib.parse.quote(store_keyword)}"
        )
        return {"search_url": search_url, "stock_url": stock_url, "work_id": work_id, "product_key": product_key}
    except Exception:
        return {"search_url": search_url, "stock_url": search_url, "work_id": None, "product_key": None}

def check_tsutaya(keyword: str, store_keyword: str = TSUTAYA_STORE_KEYWORD) -> Tuple[dict, str]:
    """TSUTAYA（各務原）の在庫チェック（1位の候補を採用）"""
    try:
        urls = build_tsutaya_urls(keyword, store_keyword=store_keyword)
        # そもそも候補が取れない＝判定不可（リンクは検索ページへ）
        if not urls.get("work_id") or not urls.get("product_key"):
            return {"text": "判定保留", "class": "border-warn", "icon": "⚠️"}, urls["stock_url"]

        res = requests.get(urls["stock_url"], headers={"User-Agent": USER_AGENT}, timeout=15)
        res.encoding = res.apparent_encoding
        if "在庫あり" in res.text:
            return {"text": "在庫あり", "class": "border-ok", "icon": "⭕️"}, urls["stock_url"]
        if "在庫なし" in res.text or "入荷予定は店舗にお問い合わせ下さい" in res.text:
            return {"text": "なし", "class": "border-ng", "icon": "❌"}, urls["stock_url"]
        return {"text": "判定保留", "class": "border-warn", "icon": "⚠️"}, urls["stock_url"]
    except Exception:
        return {"text": "エラー", "class": "border-warn", "icon": "⚠️"}, f"https://store-tsutaya.tsite.jp/search/?sheader_item-search"

def check_status(keyword):
    """全サイトの在庫状況をチェック"""
    return {
        'gifu': check_gifu_lib(keyword),
        'kani': check_kani_lib(keyword),
        'sanseido': check_sanseido(keyword),
    }

def create_result_card(site_name, icon, status, url):
    """検索結果カードのHTMLを生成"""
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

# --- Main UI ---
st.markdown("### 🔍 キーワード入力")
keyword_input = st.text_input(
    "",
    placeholder="キーワードを入力 (例: 吾輩は猫である)",
    label_visibility="collapsed",
    key="keyword_input",
)

# 検索履歴表示
if st.session_state.search_history:
    st.caption("🕒 検索履歴:")
    cols = st.columns(HISTORY_LIMIT)
    for i, hist_kw in enumerate(st.session_state.search_history[:HISTORY_LIMIT]):
        if cols[i].button(hist_kw, key=f"h_{i}", use_container_width=True):
            st.session_state.keyword_input = hist_kw
            st.rerun()

# アクションエリア
col_search, col_amazon = st.columns([1, 1])

with col_amazon:
    if keyword_input:
        amazon_url = f"https://www.amazon.co.jp/s?k={urllib.parse.quote(keyword_input)}"
        st.markdown(f"""
        <a href="{amazon_url}" target="_blank" rel="noopener noreferrer" class="btn-amazon">
            📦 Amazonで本を探す ↗
        </a>
        """, unsafe_allow_html=True)
    else:
        st.info("👆 キーワードを入力するとAmazon検索した情報に飛びます")

with col_search:
    should_search = st.button("📚 図書館・書店を検索", type="primary", use_container_width=True)

st.markdown("---")

# 検索実行ロジック
if should_search:
    if not keyword_input:
        st.warning("⚠️ キーワードを入力してください")
    else:
        add_to_history(keyword_input)
        
        st.subheader(f"「{keyword_input}」の検索結果")
        
        with st.spinner("各サイトを検索中..."):
            status = check_status(keyword_input)

            # TSUTAYA（各務原）: 1位の候補を採用して在庫ページまで作る
            tsutaya_status, tsutaya_url = check_tsutaya(keyword_input, store_keyword=TSUTAYA_STORE_KEYWORD)

            # 2x2 レイアウト（スマホでも見やすい）
            r1c1, r1c2 = st.columns(2)
            r2c1, r2c2 = st.columns(2)

            with r1c1:
                gifu_url = f"https://www1.gifu-lib.jp/winj/opac/search-standard.do?lang=ja&txt_word={urllib.parse.quote(keyword_input)}&hid_word_column=fulltext&submit_btn_searchEasy=search"
                st.markdown(create_result_card("岐阜市立図書館", "🏢", status["gifu"], gifu_url), unsafe_allow_html=True)

            with r1c2:
                kani_url = f"https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP?opr(1)=OR&DB=LIB&PID=OPWSRCH1&FLG=SEARCH&MODE=1&SORT=-3&qual(1)=MZALL&text(1)={urllib.parse.quote(keyword_input)}"
                st.markdown(create_result_card("可児市立図書館", "🌲", status["kani"], kani_url), unsafe_allow_html=True)

            with r2c1:
                sanseido_params = {
                    "shopCode": "0458",
                    "keyword": keyword_input,
                    "defaultShopCode": "",
                    "title": "",
                    "author": "",
                    "isbn": "",
                    "genreCode": "",
                    "search": "検索",
                }
                sanseido_url = f"https://www.books-sanseido.jp/booksearch/BookSearchExec.action?{urllib.parse.urlencode(sanseido_params)}"
                st.markdown(create_result_card("三省堂（岐阜）", "📖", status["sanseido"], sanseido_url), unsafe_allow_html=True)

            with r2c2:
                st.markdown(create_result_card(f"TSUTAYA（{TSUTAYA_STORE_KEYWORD}）", "🏪", tsutaya_status, tsutaya_url), unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)
