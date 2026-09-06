"""Gmail を見て、図書館の「予約本が用意できました」メールを拾う。

Apps Script（Google のサーバー）から呼ぶ案もあるが、それだとアプリを
インターネットに公開する必要がある。Mac はどのみち起動している必要が
あるので、Mac 自身が Gmail を見に行くほうが公開せずに済む。

    .venv/bin/python tools/watch_gmail.py          # 1回だけ確認
    .venv/bin/python tools/watch_gmail.py --loop   # 15分ごとに確認し続ける
    .venv/bin/python tools/watch_gmail.py --dry-run # 通知せず、拾えるかだけ見る

必要な設定（.env に書く）:
    GMAIL_ADDRESS       … 自分のGmailアドレス
    GMAIL_APP_PASSWORD  … アプリパスワード16桁（2段階認証が必要）
                          https://myaccount.google.com/apppasswords で発行
"""

from __future__ import annotations

import argparse
import email
import email.header
import imaplib
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

IMAP_HOST = "imap.gmail.com"
NOTIFY_URL = os.environ.get("BOOKFINDER_NOTIFY_URL", "http://127.0.0.1:8000/api/notify")
INTERVAL_SECONDS = 15 * 60

# 通知済みを記録するファイル。Gmail 側を既読にすると自分で読んだときに
# 取りこぼすので、こちらで持つ。
SEEN_FILE = ROOT / "book_search_app" / "data" / "notified_mail_ids.json"

# 図書館からの「用意できました」メールだけを拾う
SEARCH_QUERY = (
    '(OR (FROM "gifu-lib.jp") (FROM "kani-lib.jp"))'
)
READY_PHRASES = ("ご用意できました", "準備が整いました")

TITLE_RE = re.compile(r"書名：\s*(.+)")
BRANCH_RE = re.compile(r"受取館：\s*(.+)")
DUE_RE = re.compile(r"※(\d{4}/\d{2}/\d{2})までに")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("watch_gmail")


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    return "".join(
        chunk.decode(enc or "utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
        for chunk, enc in parts
    )


def _body_of(message: email.message.Message) -> str:
    """本文（text/plain）を取り出す。"""
    if not message.is_multipart():
        payload = message.get_payload(decode=True) or b""
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace")

    for part in message.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return ""


def parse_mail(body: str, sender: str, received: datetime) -> Optional[Dict[str, Any]]:
    """メール本文から書名・受取館・期限を取り出す。"""
    if not any(phrase in body for phrase in READY_PHRASES):
        return None

    title = TITLE_RE.search(body)
    if not title:
        return None

    is_kani = "kani-lib.jp" in sender
    branch = BRANCH_RE.search(body)
    due = DUE_RE.search(body)

    return {
        "library": "kani" if is_kani else "gifu",
        "title": title.group(1).strip(),
        "branch": branch.group(1).strip() if branch else ("カニミライブ図書館" if is_kani else None),
        # 可児市は本文に期限がある。岐阜市は無いのでサーバー側が連絡日から計算する
        "due": due.group(1) if due else None,
        "received": received.date().isoformat(),
    }


def _load_seen() -> List[str]:
    try:
        with SEEN_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_seen(ids: List[str]) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SEEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(ids[-500:], f, ensure_ascii=False, indent=2)


def fetch_new_books(address: str, app_password: str) -> tuple[List[Dict[str, Any]], List[str]]:
    """Gmail から未通知の予約本を拾う。(本のリスト, 対応するメールID) を返す。"""
    seen = set(_load_seen())
    books: List[Dict[str, Any]] = []
    handled: List[str] = []

    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(address, app_password)
        imap.select("INBOX", readonly=True)      # 既読状態を変えない

        status, data = imap.search(None, SEARCH_QUERY)
        if status != "OK":
            logger.warning("検索に失敗しました: %s", status)
            return [], []

        numbers = data[0].split()
        logger.info("図書館からのメール: %d件", len(numbers))

        for number in numbers[-50:]:              # 直近50件だけ見る
            status, raw = imap.fetch(number, "(RFC822)")
            if status != "OK" or not raw or not raw[0]:
                continue

            message = email.message_from_bytes(raw[0][1])
            message_id = _decode(message.get("Message-ID")) or number.decode()
            if message_id in seen:
                continue

            sender = _decode(message.get("From"))
            try:
                received = email.utils.parsedate_to_datetime(message.get("Date"))
            except (TypeError, ValueError):
                received = datetime.now(timezone.utc)

            parsed = parse_mail(_body_of(message), sender, received)
            if parsed:
                logger.info("見つけました: %s（%s）", parsed["title"], parsed["branch"] or parsed["library"])
                books.append(parsed)
                handled.append(message_id)

    return books, handled


def notify(books: List[Dict[str, Any]], token: str) -> bool:
    """サーバーへ渡して通知してもらう。成功したら True。"""
    request = urllib.request.Request(
        NOTIFY_URL,
        data=json.dumps({"books": books}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as res:
            logger.info("通知しました: %s", res.read().decode())
            return True
    except urllib.error.URLError as exc:
        # サーバーが止まっているときは記録を残さず、次回また拾う
        logger.error("通知に失敗しました（次回また試します）: %s", exc)
        return False


def run_once(dry_run: bool = False) -> None:
    address = os.environ.get("GMAIL_ADDRESS", "")
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not address or not app_password:
        logger.error("GMAIL_ADDRESS と GMAIL_APP_PASSWORD を .env に設定してください")
        sys.exit(1)

    from book_search_app.config import notify_token

    books, handled = fetch_new_books(address, app_password)
    if not books:
        logger.info("新しい予約本はありません")
        return

    if dry_run:
        logger.info("--dry-run のため通知しません。拾った内容:")
        for book in books:
            logger.info("  %s", json.dumps(book, ensure_ascii=False))
        return

    if notify(books, notify_token()):
        _save_seen(_load_seen() + handled)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gmail を見て予約本の到着を通知する")
    parser.add_argument("--loop", action="store_true", help="15分ごとに確認し続ける")
    parser.add_argument("--dry-run", action="store_true", help="通知せず、拾えるかだけ確認する")
    args = parser.parse_args()

    import run as runner
    runner.load_env()

    if not args.loop:
        run_once(args.dry_run)
        return

    logger.info("%d分ごとに確認します（Ctrl+C で終了）", INTERVAL_SECONDS // 60)
    while True:
        try:
            run_once(args.dry_run)
        except Exception:
            logger.exception("確認中にエラーが起きました。次回また試します")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
