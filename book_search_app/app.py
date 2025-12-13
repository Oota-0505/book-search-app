import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

# Page Config
st.set_page_config(page_title="本・図書館 横断検索", layout="wide", page_icon="📚")

# --- Custom CSS for Modern UI ---
st.markdown("""
<style>
    /* Global Styles */
    .main {
        background-color: #ffffff;
    }
    h1 {
        color: #1E3A8A; /* Dark Blue */
        font-family: 'Helvetica Neue', sans-serif;
    }
    
    /* Result Card Style */
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
    
    /* Status Colors for Borders */
    .border-ok { border-left-color: #10B981 !important; } /* Green */
    .border-ng { border-left-color: #EF4444 !important; } /* Red */
    .border-warn { border-left-color: #F59E0B !important; } /* Yellow */
    
    /* Typography */
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
    
    /* Custom Button Link (Shared style for a and button) */
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
    
    /* Search Button Styling */
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

# Helper: Add to history
def add_to_history(kw):
    if not kw: return
    if kw in st.session_state.search_history:
        st.session_state.search_history.remove(kw)
    st.session_state.search_history.insert(0, kw)
    if len(st.session_state.search_history) > 5: # Limit to 5
        st.session_state.search_history = st.session_state.search_history[:5]

# --- Logic Functions ---

def check_status(keyword):
    results = {}
    debug_info = {}
    
    # 1. Gifu Lib
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Step 1: Init Session at Top Page
        top_url = "https://www1.gifu-lib.jp/winj/opac/top.do"
        session.get(top_url, headers=headers, timeout=10)
        
        # Step 2: Search using the initialized session
        search_url = "https://www1.gifu-lib.jp/winj/opac/search-standard.do"
        params = {"txt_word": keyword, "hid_word_column": "fulltext", "submit_btn_searchEasy": "search"}
        
        res = session.get(search_url, params=params, headers=headers, timeout=10, allow_redirects=True)
        res.encoding = res.apparent_encoding
        
        debug_info['gifu_url'] = res.url
        
        # Logic Check
        if "g-mediacosmos.jp" in res.url:
             results['gifu'] = {"text": "なし", "class": "border-ng", "icon": "❌"}
        elif "該当する資料はありません" in res.text:
            results['gifu'] = {"text": "なし", "class": "border-ng", "icon": "❌"}
        else:
            soup = BeautifulSoup(res.text, 'html.parser')
            page_title = soup.title.string if soup.title else ""
            if "検索結果" in page_title or "資料検索" in page_title:
                results['gifu'] = {"text": "あり", "class": "border-ok", "icon": "⭕️"}
            else:
                 results['gifu'] = {"text": "あり", "class": "border-ok", "icon": "⭕️"}

    except Exception as e:
        results['gifu'] = {"text": "エラー", "class": "border-warn", "icon": "⚠️"}
        debug_info['gifu_error'] = str(e)

    # 2. Kani Lib
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        
        init_url = "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCH1.CSP?DB=LIB&MODE=1"
        session.get(init_url, timeout=10)
        
        url = "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP"
        params = {"text(1)": keyword, "opr(1)": "OR", "DB": "LIB", "PID": "OPWSRCH1", "FLG": "SEARCH", "MODE": "1", "SORT": "-3", "qual(1)": "MZALL"}
        
        res = session.get(url, params=params, timeout=15)
        res.encoding = res.apparent_encoding
        
        if "該当する資料はありません" in res.text or "検索結果 0件" in res.text:
            results['kani'] = {"text": "なし", "class": "border-ng", "icon": "❌"}
        elif "○ 在架あり" in res.text:
            results['kani'] = {"text": "在庫あり", "class": "border-ok", "icon": "⭕️"}
        elif "貸出中" in res.text or "予約" in res.text:
            results['kani'] = {"text": "貸出中", "class": "border-warn", "icon": "⚠️"}
        else:
            results['kani'] = {"text": "あり", "class": "border-ok", "icon": "⭕️"}
    except:
        results['kani'] = {"text": "エラー", "class": "border-warn", "icon": "⚠️"}

    # 3. Sanseido
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
            results['sanseido'] = {"text": f"{match.group(1)}件", "class": "border-ok", "icon": "⭕️"}
        elif "検索結果：0件" in res.text:
            results['sanseido'] = {"text": "なし", "class": "border-ng", "icon": "❌"}
        else:
            results['sanseido'] = {"text": "あり", "class": "border-ok", "icon": "⭕️"}
    except:
        results['sanseido'] = {"text": "エラー", "class": "border-warn", "icon": "⚠️"}
        
    return results, debug_info

# --- Main Execution ---

keyword_input = st.text_input("", placeholder="キーワードを入力 (例: 吾輩は猫である)", label_visibility="collapsed")

# History UI
if st.session_state.search_history:
    st.write("🕒 検索履歴:") 
    cols = st.columns(6) 
    for i, hist_kw in enumerate(st.session_state.search_history):
        if i < 5: 
            if cols[i].button(hist_kw, key=f"h_{i}"):
                keyword_input = hist_kw 

# Search Action
if st.button("🔍 検索", type="primary", use_container_width=True) or (keyword_input and keyword_input not in st.session_state.search_history and len(keyword_input) > 1):
    if not keyword_input:
        st.warning("キーワードを入力してください")
    else:
        add_to_history(keyword_input)
        with st.spinner("検索中..."):
            status, debug = check_status(keyword_input)
            
            # --- Result Cards ---
            col1, col2, col3 = st.columns(3)
            
            # 1. Gifu
            with col1:
                s = status['gifu']
                gifu_search_url = f"https://www1.gifu-lib.jp/winj/opac/search-standard.do?txt_word={urllib.parse.quote(keyword_input)}&hid_word_column=fulltext&submit_btn_searchEasy=search"
                st.markdown(f"""
                <div class="result-card {s['class']}">
                    <div class="site-name">🏢 岐阜市立図書館</div>
                    <div class="status-text">{s['icon']} {s['text']}</div>
                    <a href="{gifu_search_url}" target="_blank" rel="noopener noreferrer" class="btn-link">結果を開く ↗</a>
                </div>
                """, unsafe_allow_html=True)
                st.caption("※ トップページに飛ばされた場合は、一度トップページを開いてから再度お試しください。")

            # 2. Kani
            with col2:
                s = status['kani']
                st.markdown(f"""
                <div class="result-card {s['class']}">
                    <div class="site-name">🌲 可児市立図書館</div>
                    <div class="status-text">{s['icon']} {s['text']}</div>
                    <a href="https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP?opr(1)=OR&DB=LIB&PID=OPWSRCH1&FLG=SEARCH&MODE=1&SORT=-3&qual(1)=MZALL&text(1)={urllib.parse.quote(keyword_input)}" target="_blank" rel="noopener noreferrer" class="btn-link">結果を開く ↗</a>
                </div>
                """, unsafe_allow_html=True)

            # 3. Sanseido (Full params)
            with col3:
                s = status['sanseido']
                sanseido_params = {
                    "shopCode": "0458",
                    "keyword": keyword_input,
                    "defaultShopCode": "",
                    "title": "",
                    "author": "",
                    "isbn": "",
                    "genreCode": "",
                    "search": "検索"
                }
                sanseido_qs = urllib.parse.urlencode(sanseido_params)
                
                st.markdown(f"""
                <div class="result-card {s['class']}">
                    <div class="site-name">📖 三省堂書店</div>
                    <div class="status-text">{s['icon']} {s['text']}</div>
                    <a href="https://www.books-sanseido.jp/booksearch/BookSearchExec.action?{sanseido_qs}" target="_blank" rel="noopener noreferrer" class="btn-link">結果を開く ↗</a>
                </div>
                """, unsafe_allow_html=True)

st.markdown("---")
