import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

# Page Config
st.set_page_config(page_title="本・図書館 横断検索", layout="wide", page_icon="📚")

# Constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HISTORY_LIMIT = 5

# --- Custom CSS for Modern UI ---
st.markdown("""
<style>
    .main {
        background-color: #ffffff;
    }
    h1 {
        color: #1E3A8A;
        font-family: 'Helvetica Neue', sans-serif;
    }
    .result-card {
        background-color: #f8f9fa;
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
        border-left: 5px solid #ddd;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        transition: transform 0.2s;
    }
    .result-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .border-ok { border-left-color: #10B981 !important; }
    .border-ng { border-left-color: #EF4444 !important; }
    .border-warn { border-left-color: #F59E0B !important; }
    .site-name {
        font-size: 1.1rem;
        font-weight: 700;
        color: #4B5563;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .status-text {
        font-size: 1.5rem;
        font-weight: 800;
        margin: 10px 0;
    }
    .btn-link {
        display: block;
        width: 100%;
        text-align: center;
        background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);
        color: white !important;
        text-decoration: none;
        padding: 10px 0;
        border-radius: 8px;
        font-weight: 600;
        margin-top: 15px;
        box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
        border: none;
        cursor: pointer;
        font-size: 1rem;
        line-height: 1.5;
    }
    .btn-link:hover {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);
    }
    div.stButton > button {
        width: 100%;
        background: linear-gradient(90deg, #4F46E5 0%, #3B82F6 100%);
        color: white !important;
        font-weight: bold;
        border: none;
        padding: 0.6rem 1rem;
        border-radius: 8px;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(59, 130, 246, 0.3);
    }
    div.stButton > button:hover {
        background: linear-gradient(90deg, #4338CA 0%, #2563EB 100%);
        box-shadow: 0 6px 8px rgba(59, 130, 246, 0.4);
        transform: translateY(-1px);
        color: white !important;
        border-color: transparent !important;
    }
    div.stButton > button:active {
        transform: translateY(1px);
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
    }
    div.stButton > button:focus {
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.5);
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("📚 Book Finder")
st.caption("岐阜市図書館・可児市図書館・三省堂書店を一括検索")

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
        
        # 判定
        if "g-mediacosmos.jp" in res.url or "該当する資料はありません" in res.text:
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
    """三省堂書店の在庫チェック"""
    try:
        url = "https://www.books-sanseido.jp/booksearch/BookSearchExec.action"
        params = {
            "shopCode": "0458", "keyword": keyword, "defaultShopCode": "",
            "title": "", "author": "", "isbn": "", "genreCode": "", "search": "検索"
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.encoding = res.apparent_encoding
        
        match = re.search(r'(\d+)件中', res.text)
        if match and match.group(1) != "0":
            return {"text": f"{match.group(1)}件", "class": "border-ok", "icon": "⭕️"}
        elif "検索結果：0件" in res.text:
            return {"text": "なし", "class": "border-ng", "icon": "❌"}
        return {"text": "あり", "class": "border-ok", "icon": "⭕️"}
    except Exception:
        return {"text": "エラー", "class": "border-warn", "icon": "⚠️"}

def check_status(keyword):
    """全サイトの在庫状況をチェック"""
    return {
        'gifu': check_gifu_lib(keyword),
        'kani': check_kani_lib(keyword),
        'sanseido': check_sanseido(keyword)
    }

def create_result_card(site_name, icon, status, url):
    """検索結果カードのHTMLを生成"""
    return f"""
    <div class="result-card {status['class']}">
        <div class="site-name">{icon} {site_name}</div>
        <div class="status-text">{status['icon']} {status['text']}</div>
        <a href="{url}" target="_blank" rel="noopener noreferrer" class="btn-link">結果を開く ↗</a>
    </div>
    """

# --- Main UI ---
keyword_input = st.text_input("", placeholder="キーワードを入力 (例: 吾輩は猫である)", label_visibility="collapsed")

# 検索履歴表示
if st.session_state.search_history:
    st.write("🕒 検索履歴:")
    cols = st.columns(6)
    for i, hist_kw in enumerate(st.session_state.search_history[:HISTORY_LIMIT]):
        if cols[i].button(hist_kw, key=f"h_{i}"):
            keyword_input = hist_kw

# 検索実行
should_search = st.button("🔍 検索", type="primary", use_container_width=True)
if should_search or (keyword_input and keyword_input not in st.session_state.search_history and len(keyword_input) > 1):
    if not keyword_input:
        st.warning("キーワードを入力してください")
    else:
        add_to_history(keyword_input)
        with st.spinner("検索中..."):
            status = check_status(keyword_input)
            
            col1, col2, col3 = st.columns(3)
            
            # 岐阜市立図書館
            with col1:
                # lang=jaパラメータを追加してPC版として認識させる
                gifu_url = f"https://www1.gifu-lib.jp/winj/opac/search-standard.do?lang=ja&txt_word={urllib.parse.quote(keyword_input)}&hid_word_column=fulltext&submit_btn_searchEasy=search"
                st.markdown(create_result_card("🏢 岐阜市立図書館", "", status['gifu'], gifu_url), unsafe_allow_html=True)
                # st.caption("※ スマホでトップページに飛ばされた場合は、一度トップページを開いてから再度お試しください。")
            
            # 可児市立図書館
            with col2:
                kani_url = f"https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP?opr(1)=OR&DB=LIB&PID=OPWSRCH1&FLG=SEARCH&MODE=1&SORT=-3&qual(1)=MZALL&text(1)={urllib.parse.quote(keyword_input)}"
                st.markdown(create_result_card("🌲 可児市立図書館", "", status['kani'], kani_url), unsafe_allow_html=True)
            
            # 三省堂書店
            with col3:
                sanseido_params = {
                    "shopCode": "0458", "keyword": keyword_input, "defaultShopCode": "",
                    "title": "", "author": "", "isbn": "", "genreCode": "", "search": "検索"
                }
                sanseido_url = f"https://www.books-sanseido.jp/booksearch/BookSearchExec.action?{urllib.parse.urlencode(sanseido_params)}"
                st.markdown(create_result_card("📖 三省堂書店", "", status['sanseido'], sanseido_url), unsafe_allow_html=True)

st.markdown("---")
