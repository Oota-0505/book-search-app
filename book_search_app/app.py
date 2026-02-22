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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

# ============================================================================
# サードパーティライブラリ
# ============================================================================
import requests
import streamlit as st
from bs4 import BeautifulSoup


# ============================================================================
# ロギング設定
# ============================================================================
# ────────────────────────────────────────────────────────────────────────────
# 【学習メモ】Python の logging モジュールとは？
#
# print() によるデバッグは手軽ですが、以下の問題があります：
#   - 本番環境でも常に出力されてしまう
#   - 重要度（エラーか通知かデバッグか）が区別できない
#   - ファイルへの保存やローテーションができない
#
# 標準ライブラリの logging モジュールを使うと：
#   - ログレベル（DEBUG / INFO / WARNING / ERROR / CRITICAL）で重要度を管理できる
#   - ファイルへの書き込みや日付ローテーションが設定だけで実現できる
#   - 開発環境と本番環境でログの出力先・レベルを切り替えられる
#
# 主要な登場人物：
#   Logger    → ログを記録する窓口。アプリコードから呼び出す。
#   Handler   → 出力先（ファイル・コンソール・メール等）ごとに定義する。
#   Formatter → ログ1行の書式（日時・レベル・関数名・メッセージ）を定義する。
# ────────────────────────────────────────────────────────────────────────────


def _setup_logger(name: str = "book_finder") -> logging.Logger:
    """
    アプリケーション用ロガーを設定して返す。

    出力先:
        1. コンソール（sys.stderr）: DEBUG 以上すべてのログ
        2. logs/app.log（日付ローテーション）: INFO 以上のログ

    Args:
        name: ロガー名。同じ名前を渡すと同一インスタンスが返る（シングルトン）。

    Returns:
        設定済みの Logger インスタンス
    """
    # ── ログ保存先ディレクトリの作成 ──────────────────────────────────────
    # pathlib.Path: os.path の代替となるオブジェクト指向のパス操作クラス。
    #   OS ごとのパス区切り文字（/ や \）を意識せずに書ける。
    # mkdir(exist_ok=True): ディレクトリがすでに存在してもエラーを出さない。
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # ── Logger インスタンスの取得 ──────────────────────────────────────────
    # logging.getLogger(name) は同じ name に対して常に同一インスタンスを返す。
    # アプリ全体で1つのロガーを共有できる（グローバルシングルトン）。
    logger = logging.getLogger(name)

    # Streamlit はページ操作のたびにスクリプトを再実行するため、
    # ハンドラが二重登録されないようにガードする。
    if logger.handlers:
        return logger

    # ── ログレベルの設定 ──────────────────────────────────────────────────
    # ロガー本体のレベルを最低（DEBUG）にして、
    # ハンドラ側で実際に出力するレベルを制限するのがよくある設計パターン。
    #
    # レベル一覧（低い順）：
    #   DEBUG    (10) : 開発中の詳細情報（変数の値、処理の流れなど）
    #   INFO     (20) : 正常動作の記録（検索実行・完了など）
    #   WARNING  (30) : 問題ではないが注意が必要（タイムアウト、404 など）
    #   ERROR    (40) : 処理が失敗した場合（例外の発生など）
    #   CRITICAL (50) : システム全体に影響する重大エラー
    logger.setLevel(logging.DEBUG)

    # ── フォーマッタの定義 ─────────────────────────────────────────────────
    # ログの各行に含める情報と書式を定義する。
    # 利用できる主な変数：
    #   %(asctime)s   : ログ記録日時        例) 2026-02-22 10:00:00
    #   %(levelname)s : ログレベル名        例) INFO
    #   %-8s          : 8文字幅・左寄せ（レベル名を揃えて読みやすくする）
    #   %(funcName)s  : ログを記録した関数名  例) check_gifu_lib
    #   %(message)s   : ログ本文（logger.info("ここ") の "ここ" の部分）
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── ファイルハンドラ：TimedRotatingFileHandler ─────────────────────────
    # ログファイルを指定した周期で自動的に切り替えるハンドラ（ローテーション）。
    # 1ファイルに無制限にログが溜まるのを防ぎ、古いログを自動削除できる。
    #
    # 引数の説明：
    #   filename    : 書き込み先ファイルパス
    #   when        : ローテーションのタイミング
    #                 "midnight" = 毎日0時, "h" = 毎時, "W0" = 毎週月曜 など
    #   backupCount : 保持する古いファイル数（30 → 約30日分保持、超えたら削除）
    #   encoding    : 日本語が文字化けしないよう UTF-8 を指定
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "app.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)   # ファイルには INFO 以上のみ記録する
    file_handler.setFormatter(formatter)

    # ── コンソールハンドラ：StreamHandler ─────────────────────────────────
    # デフォルトで sys.stderr（標準エラー出力）に書き出すハンドラ。
    # 開発中にターミナルでリアルタイムにログを確認するために追加する。
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)   # コンソールには DEBUG 以上すべて出力
    console_handler.setFormatter(formatter)

    # ── ハンドラをロガーに登録 ────────────────────────────────────────────
    # addHandler() で複数の出力先を同時に追加できる。
    # 下記の設定後、logger.info("test") を呼ぶと
    # ファイルとコンソールの両方に同時に出力される。
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# モジュール読み込みと同時にロガーを初期化する。
# モジュール内の全関数からこの変数 `logger` を参照してログを記録する。
logger = _setup_logger()


# ============================================================================
# データクラス
# ============================================================================

@dataclass(frozen=True)
class BookStatus:
    """
    各サイトの在庫状況を表す不変データクラス。

    frozen=True によりインスタンス作成後の値変更を禁止（イミュータブル設計）。
    辞書（dict）と違い、属性名が明示されるため IDE の補完・型チェックが効く。

    Attributes:
        text:      表示テキスト（例: "在庫あり", "なし", "エラー"）
        css_class: カードのアクセント色 CSS クラス
        icon:      ステータスアイコン（例: "⭕️", "❌", "⚠️"）
    """
    text: str
    css_class: str
    icon: str


# ============================================================================
# 設定・定数
# ============================================================================

# ── Streamlit ページ設定（スクリプト内で最初に呼ぶ必要がある）──────────────
st.set_page_config(page_title="Book Finder", layout="wide", page_icon="📚")

# ── HTTP リクエスト設定 ──────────────────────────────────────────────────────
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS: Dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
TIMEOUT_SHORT: int = 10   # 秒：通常の GET リクエスト用
TIMEOUT_MEDIUM: int = 20  # 秒：レスポンスが遅いサイト（ミライブ・各務原BCなど）用

# ── アプリ設定 ──────────────────────────────────────────────────────────────
HISTORY_LIMIT: int = 5
KUSA_BOOKS_KEYWORD: str = "各務原店"  # 各務原BC の店舗検索キーワード

# ── 在庫ステータス定数 ──────────────────────────────────────────────────────
# よく使うステータスをモジュールレベルで定義し、関数内で使い回す。
# BookStatus は frozen=True（不変）なので、定数として安全に共有できる。
_S_AVAILABLE = BookStatus("在庫あり", "accent-ok",   "⭕️")
_S_NONE      = BookStatus("なし",     "accent-ng",   "❌")
_S_LENDING   = BookStatus("貸出中",   "accent-warn", "⚠️")
_S_PENDING   = BookStatus("判定保留", "accent-warn", "⚠️")
_S_ERROR     = BookStatus("エラー",   "accent-warn", "⚠️")

# ── カード背景画像・静的アセット ─────────────────────────────────────────
# 画像・CSS はすべて static/ 配下に集約（images / css）。
_APP_DIR: Path = Path(__file__).parent
_STATIC_DIR: Path = _APP_DIR / "static"
_IMAGES_DIR: Path = _STATIC_DIR / "images"

CARD_BG_PATHS: Dict[str, Path] = {
    "gifu":     _IMAGES_DIR / "メディコス.webp",
    "kani":     _IMAGES_DIR / "ミライブ.webp",
    "sanseido": _IMAGES_DIR / "岐阜駅本屋.png",
    "tsutaya":  _IMAGES_DIR / "各務原BC.jpg",
}

# ── 背景画像のパス（松本十畳のみ）────────────────────────────────────────────
_BG_IMAGE_PATH: Path = _IMAGES_DIR / "松本十畳.jpg"


# ============================================================================
# 背景画像ローダー
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
    if s in (".jpg", ".jpeg"):
        return "image/jpeg"
    return "image/jpeg"


@st.cache_resource
def _load_card_images_base64() -> Dict[str, str]:
    """
    4枚のカード背景画像を読み込み、data URI 文字列の辞書で返す。

    Returns:
        キーは "gifu" | "kani" | "sanseido" | "tsutaya"。
        値は "data:image/xxx;base64,..." またはファイルがない場合は空文字列。
    """
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
# CSS ビルダー
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
    アプリ全体の CSS を組み立てて返す。

    外部 CSS ファイルを読み込み、背景画像を base64 で埋め込む。
    Streamlit Cloud を含む任意のホスティング環境で画像が確実に表示される。

    Args:
        bg_base64: base64 エンコード済みの JPEG 文字列（空文字ならグラデーション背景）

    Returns:
        <style> タグを含む HTML 文字列
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
    """セッションステートを初期化する（未設定キーのみ処理）。"""
    if "search_history" not in st.session_state:
        st.session_state.search_history = []


def _add_to_history(keyword: str) -> None:
    """
    検索履歴にキーワードを追加する。

    既存のキーワードは先頭に移動し、HISTORY_LIMIT 件を超えた分は削除する。

    Args:
        keyword: 追加する検索キーワード
    """
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
    """
    メディコス（岐阜市立図書館）の在庫をチェックする。

    Args:
        keyword: 検索キーワード

    Returns:
        在庫状況を表す BookStatus
    """
    logger.info("メディコスを検索: '%s'", keyword)
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        # セッション Cookie を取得するためにトップページへアクセス
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
    """
    ミライブ（可児市立図書館）の在庫をチェックする。

    Args:
        keyword: 検索キーワード

    Returns:
        在庫状況を表す BookStatus
    """
    logger.info("ミライブを検索: '%s'", keyword)
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        session.get(
            "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCH1.CSP?DB=LIB&MODE=1",
            timeout=TIMEOUT_SHORT,
        )

        res = session.get(
            "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP",
            params={
                "text(1)": keyword,
                "opr(1)":  "OR",
                "DB":      "LIB",
                "PID":     "OPWSRCH1",
                "FLG":     "SEARCH",
                "MODE":    "1",
                "SORT":    "-3",
                "qual(1)": "MZALL",
            },
            timeout=TIMEOUT_MEDIUM,
        )
        res.encoding = res.apparent_encoding

        if "該当する資料はありません" in res.text or "検索結果 0件" in res.text:
            logger.info("ミライブ: 該当なし")
            return _S_NONE
        if "○ 在架あり" in res.text:
            logger.info("ミライブ: 在庫あり")
            return _S_AVAILABLE
        if "貸出中" in res.text or "予約" in res.text:
            logger.info("ミライブ: 貸出中")
            return _S_LENDING

        logger.info("ミライブ: 在庫あり（詳細不明）")
        return _S_AVAILABLE

    except requests.exceptions.Timeout:
        logger.warning("ミライブ: タイムアウト (keyword='%s')", keyword)
        return _S_ERROR
    except requests.exceptions.RequestException as exc:
        logger.error("ミライブ: リクエストエラー - %s", exc)
        return _S_ERROR


def check_sanseido(keyword: str) -> BookStatus:
    """
    岐阜駅本屋の在庫をチェックする（書籍のみ。電子書籍は在庫に含めない）。

    Args:
        keyword: 検索キーワード

    Returns:
        在庫状況を表す BookStatus
    """
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

        # 在庫記号: ○=書籍在庫あり, ×=なし, △/▲=電子書籍等（書籍のみの在庫表示のため無視）
        stock_marks = re.findall(r"在庫：\s*([○×△▲])", res.text)
        if stock_marks:
            # 書籍（○）が1件でもあれば在庫あり。△・▲は電子書籍のためカウントしない。
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


def _extract_first_tsutaya_work_id(html: str) -> Optional[str]:
    """
    各務原BC（草叢BOOKS）キーワード検索結果 HTML から1位の workId を抽出する。

    Args:
        html: 検索結果ページの HTML 文字列

    Returns:
        workId 文字列。見つからない場合は None。
    """
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
    """
    各務原BC の select ページを開き、productKey（ISBN/JAN）を抽出する。

    Args:
        work_id: 作品 ID

    Returns:
        productKey 文字列。見つからない場合は None。
    """
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
    """
    各務原BC の検索 URL と在庫確認 URL を生成する。

    在庫 URL の生成に必要な workId・productKey が取得できない場合は
    フォールバックとして検索 URL を両方の値に使用する。

    Args:
        keyword: 検索キーワード

    Returns:
        (search_url, stock_url) のタプル
    """
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
    """
    各務原BCの在庫をチェックする。

    Args:
        keyword: 検索キーワード

    Returns:
        (在庫状況を表す BookStatus, 結果表示 URL) のタプル
    """
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


def check_all_sites(keyword: str) -> Dict[str, BookStatus]:
    """
    図書館3館の在庫状況を一括チェックする。

    Args:
        keyword: 検索キーワード

    Returns:
        サイトキーと BookStatus のマッピング辞書
    """
    return {
        "gifu":     check_gifu_lib(keyword),
        "kani":     check_kani_lib(keyword),
        "sanseido": check_sanseido(keyword),
    }


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
    """Amazon の検索 URL を生成する。"""
    return f"https://www.amazon.co.jp/s?k={urllib.parse.quote(keyword)}"


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
    """
    検索結果カードの HTML を生成する。

    背景画像 + 半透明オーバーレイ + コンテンツの 3 層構造。
    bg_image_url が空の場合はグラデーション背景にフォールバックする。

    Args:
        site_name:    サイト名
        icon:         サイトアイコン文字
        status:       在庫状況
        url:          「結果を開く」リンク先 URL
        bg_image_url: カード背景画像の URL（省略可）

    Returns:
        HTML 文字列
    """
    pill_class = _PILL_CLASS_MAP.get(status.css_class, "pill-warn")
    # data URI の場合は url('...') で囲む（引用符のエスケープ回避）
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
    """検索履歴ボタンを表示する。履歴がない場合は何も表示しない。"""
    if not st.session_state.search_history:
        return
    st.caption("🕒 検索履歴:")
    cols = st.columns(HISTORY_LIMIT)
    for i, hist_kw in enumerate(st.session_state.search_history[:HISTORY_LIMIT]):
        if cols[i].button(hist_kw, key=f"h_{i}", use_container_width=True):
            st.session_state.keyword_input = hist_kw
            st.rerun()


def _render_search_results(keyword: str) -> None:
    """
    検索を実行し、結果カードを表示する。

    Args:
        keyword: 検索キーワード
    """
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

    status = check_all_sites(keyword)
    tsutaya_status, tsutaya_url = check_tsutaya(keyword)

    loader.empty()

    card_images = _load_card_images_base64()
    logger.info(
        "検索完了: メディコス=%s ミライブ=%s 岐阜駅本屋=%s 各務原BC=%s",
        status["gifu"].text,
        status["kani"].text,
        status["sanseido"].text,
        tsutaya_status.text,
    )

    # 4枚のカードを1つのグリッドで同時表示（Streamlit columns による段階表示を回避）
    cards_html = (
        _create_result_card("メディコス", "🏢", status["gifu"], build_gifu_url(keyword), card_images["gifu"])
        + _create_result_card("ミライブ", "🌲", status["kani"], build_kani_url(keyword), card_images["kani"])
        + _create_result_card("岐阜駅本屋", "📖", status["sanseido"], build_sanseido_url(keyword), card_images["sanseido"])
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

    bg_base64 = _load_bg_base64()
    st.markdown(_build_app_css(bg_base64), unsafe_allow_html=True)

    # ── ヒーローセクション（本＋虫眼鏡アイコンはレンズが右上向き）────────────
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
                    <g filter="url(#hero-glass)" transform="translate(18, 6)">
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

    # ── マイページリンク（メディコス・ミライブのログインへ）────────────────
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
        amazon_url = (
            build_amazon_url(keyword_input)
            if keyword_input
            else "https://www.amazon.co.jp/s?k="
        )
        st.markdown(
            f'<a href="{amazon_url}" target="_blank" rel="noopener noreferrer" class="btn-amazon">'
            f"📦 Amazonで本を探す ↗"
            f"</a>",
            unsafe_allow_html=True,
        )

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
