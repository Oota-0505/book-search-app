# 実装タスクプラン（上から順にやればできる手順書）

- 作成: 2026-09-05
- 目的: ①Web Push を学ぶ（Laravel の予習）→ ②Mac 無しでも使えるようにする
- 使い方: **上から順にやってください。** 各ステップに「やること・コード・確認方法」があります
- 前提: [`push_notification_report.md`](push_notification_report.md) / [`hosting_proposal.md`](hosting_proposal.md) の調査結果に基づく

---

## 0. 全体の流れ

```
Phase A  Web Push をローカルで作る      ← 学びの9割はここ。Laravelにそのまま効く
Phase B  公開に耐える形に整える（認証）  ← ここを飛ばすと「誰でも見れる」状態になる
Phase C  Cloud Run へデプロイ           ← Mac 不要になる
Phase D  スマホで再登録・再購読          ← 1分で終わる
Phase E  Gmail と繋ぐ                   ← 実用化
```

### なぜこの順番か

プッシュの購読は**ドメインに紐づく**ので、デプロイ後に作り直しが要ります。
それでも A を先にする理由は、**デプロイ後に開発すると1行直すたびに再デプロイ（1〜2分）**になるからです。
再購読は「アイコン削除 → 再追加 → ベルをタップ」の**1分**で済むので、A が先のほうが圧倒的に速く回ります。

### 各Phaseの独立性

- **Phase A だけやって終わりでもOK**（Mac起動中は通知が届く）
- **Phase B〜C だけやってもOK**（通知なしで Mac 不要になる）

---

# Phase A — Web Push をローカルで作る

> ゴール: 画面の「🔔 通知をオンにする」を押す → `curl` で叩くと iPhone に通知が出て、アイコンに数字がつく

## A-1. ライブラリを入れる

```bash
cd "/Users/monet/Documents/Book Research"
.venv/bin/python -m pip install pywebpush py-vapid
```

`requirements.txt` に追記：

```
pywebpush==2.0.3
py-vapid==1.9.2
```

- [ ] 完了

---

## A-2. VAPID 鍵ペアを作る

VAPID は「このプッシュは確かにあなたのサーバーが送った」を証明する鍵です。
**Laravel では `php artisan webpush:vapid` が同じことをします。**

`tools/make_vapid.py` を新規作成：

```python
"""VAPID 鍵ペアを生成する。

    .venv/bin/python tools/make_vapid.py

秘密鍵は book_search_app/data/vapid_private.pem に保存する（.gitignore 済み）。
公開鍵はブラウザに渡す文字列として表示する。
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DATA_DIR = Path(__file__).resolve().parent.parent / "book_search_app" / "data"
PRIVATE_KEY_PATH = DATA_DIR / "vapid_private.pem"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists():
        print(f"既に存在します: {PRIVATE_KEY_PATH}")
        print("作り直すと既存の購読がすべて無効になります。消してから再実行してください。")
        private_key = serialization.load_pem_private_key(
            PRIVATE_KEY_PATH.read_bytes(), password=None
        )
    else:
        private_key = ec.generate_private_key(ec.SECP256R1())
        PRIVATE_KEY_PATH.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        PRIVATE_KEY_PATH.chmod(0o600)
        print(f"秘密鍵を保存しました: {PRIVATE_KEY_PATH}")

    # ブラウザに渡す applicationServerKey（非圧縮形式の base64url）
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key = base64.urlsafe_b64encode(raw).decode().rstrip("=")

    print()
    print("VAPID_PUBLIC_KEY（config.py に貼る）:")
    print(f'  "{public_key}"')


if __name__ == "__main__":
    main()
```

実行：

```bash
.venv/bin/python tools/make_vapid.py
```

- [ ] 秘密鍵ができた（`book_search_app/data/vapid_private.pem`）
- [ ] 公開鍵の文字列を控えた

> ⚠️ **秘密鍵は絶対にコミットしない**こと。`book_search_app/data/` は `.gitignore` 済みなので大丈夫です。

---

## A-3. 設定を足す

`book_search_app/config.py` の末尾に追記：

```python
# ── Web Push ───────────────────────────────────────────────────
# A-2 で表示された公開鍵を貼る
VAPID_PUBLIC_KEY: Final[str] = "ここに貼る"
VAPID_PRIVATE_KEY_PATH: Final[Path] = DATA_DIR / "vapid_private.pem"

# ⚠️ Apple は mailto: か HTTPS URL 以外だと 403 を返す（Laravel の VAPID_SUBJECT と同じ）
VAPID_SUBJECT: Final[str] = "mailto:あなたのメールアドレス"

# 購読情報の保存先
SUBSCRIPTIONS_FILE: Final[Path] = DATA_DIR / "push_subscriptions.json"
```

- [ ] 完了

---

## A-4. 購読情報を保存する仕組み

`book_search_app/push.py` を新規作成：

```python
"""Web Push の購読管理と送信。

Laravel では laravel-notification-channels/webpush が
`push_subscriptions` テーブルと HasPushSubscriptions trait で
同じ役割を担う。
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List

from pywebpush import WebPushException, webpush

from .config import (
    DATA_DIR,
    SUBSCRIPTIONS_FILE,
    VAPID_PRIVATE_KEY_PATH,
    VAPID_SUBJECT,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _load() -> List[Dict[str, Any]]:
    try:
        with SUBSCRIPTIONS_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("購読情報の読み込みに失敗: %s", exc)
        return []


def _save(subscriptions: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SUBSCRIPTIONS_FILE.open("w", encoding="utf-8") as f:
        json.dump(subscriptions, f, ensure_ascii=False, indent=2)


def add(subscription: Dict[str, Any]) -> None:
    """購読を登録する（同じ endpoint は上書き）。"""
    with _lock:
        subscriptions = [s for s in _load() if s.get("endpoint") != subscription.get("endpoint")]
        subscriptions.append(subscription)
        _save(subscriptions)
        logger.info("購読を登録しました（現在 %d 件）", len(subscriptions))


def remove(endpoint: str) -> None:
    with _lock:
        subscriptions = [s for s in _load() if s.get("endpoint") != endpoint]
        _save(subscriptions)


def send(title: str, body: str, url: str = "/", badge_count: int | None = None) -> Dict[str, int]:
    """登録済みの全端末へ通知を送る。

    ⚠️ iOS は showNotification を伴わない push を「サイレント」とみなし、
       数回続くと購読を解除する。payload には必ず表示内容を入れること。
    """
    payload = json.dumps(
        {"title": title, "body": body, "url": url, "count": badge_count},
        ensure_ascii=False,
    )

    sent = 0
    expired: List[str] = []

    for subscription in _load():
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=str(VAPID_PRIVATE_KEY_PATH),
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                # 端末側で購読が失効している。掃除する
                expired.append(subscription["endpoint"])
                logger.info("失効した購読を削除します: %s", status)
            else:
                logger.error("プッシュ送信に失敗: %s", exc)

    for endpoint in expired:
        remove(endpoint)

    return {"sent": sent, "expired": len(expired)}
```

- [ ] 完了

---

## A-5. API を追加する

`book_search_app/main.py` に追記：

```python
# import に追加
from fastapi import Body
from . import push
from .config import VAPID_PUBLIC_KEY


@app.get("/api/push/key", include_in_schema=False)
async def push_key() -> JSONResponse:
    """ブラウザが購読するときに使う公開鍵を返す。"""
    return JSONResponse({"key": VAPID_PUBLIC_KEY})


@app.post("/api/push/subscribe", include_in_schema=False)
async def push_subscribe(subscription: dict = Body(...)) -> JSONResponse:
    if not subscription.get("endpoint"):
        return JSONResponse({"error": "購読情報が不正です"}, status_code=400)
    push.add(subscription)
    return JSONResponse({"ok": True})


@app.post("/api/push/test", include_in_schema=False)
def push_test() -> JSONResponse:
    """動作確認用。Phase E で Gmail 連携に置き換える。"""
    result = push.send(
        title="📚 予約本が届きました",
        body="メディコスで1冊、受け取り待ちです",
        url="/?from=push",
        badge_count=1,
    )
    return JSONResponse(result)
```

- [ ] 完了

---

## A-6. Service Worker にハンドラを足す

`book_search_app/static/sw.js` の**末尾**に追記：

```javascript
/* ── プッシュ通知 ───────────────────────────────────────────── */

self.addEventListener("push", (event) => {
    const data = event.data ? event.data.json() : {};

    event.waitUntil((async () => {
        // ⚠️ iOS では showNotification を必ず呼ぶこと。
        //    省略すると「サイレントpush」とみなされ、購読を解除される。
        await self.registration.showNotification(data.title || "Book Finder", {
            body: data.body || "",
            icon: "/static/icons/icon-192.png",
            badge: "/static/icons/icon-192.png",
            data: { url: data.url || "/" },
        });

        // アイコンに数字を出す（iOS 16.4+ / ホーム画面追加済みのときだけ効く）
        if (typeof data.count === "number" && self.navigator.setAppBadge) {
            await self.navigator.setAppBadge(data.count);
        }
    })());
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || "/";

    event.waitUntil((async () => {
        // ⚠️ iOS では clients.openWindow() で別オリジンへ飛べない。
        //    必ず自分のオリジン内へ遷移させ、案内リンクは画面側に出すこと。
        const windows = await self.clients.matchAll({
            type: "window",
            includeUncontrolled: true,
        });

        for (const client of windows) {
            if (new URL(client.url).origin === self.location.origin) {
                await client.navigate(url);
                return client.focus();
            }
        }
        return self.clients.openWindow(url);
    })());
});
```

> ⚠️ **`VERSION` を `"v1"` → `"v2"` に上げること。** 上げないと古いSWが端末に残り続けます。

- [ ] 追記した
- [ ] `VERSION` を上げた

---

## A-7. 画面に「通知をオンにする」ボタンを足す

`book_search_app/templates/index.html` の `.actions` の下に：

```html
<button type="button" class="btn btn-ghost" id="push-btn" hidden>
    🔔 通知をオンにする
</button>
```

`book_search_app/static/js/app.js` の末尾（IIFE の中）に：

```javascript
// ── プッシュ通知 ────────────────────────────────────────────
const pushBtn = document.getElementById("push-btn");

/** base64url の公開鍵を Uint8Array に変換する。
 *  ⚠️ Safari は文字列のままだと受け付けないので、この変換が必須。 */
function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function enablePush() {
    // ⚠️ iOS では「クリックハンドラの中」でしか許可を求められない。
    //    setTimeout やページ読み込み時に呼ぶと黙って無視される。
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
        renderMessage("⚠️ 通知が許可されませんでした。設定アプリから変更できます。");
        return;
    }

    const registration = await navigator.serviceWorker.ready;
    const { key } = await (await fetch("/api/push/key")).json();

    const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,               // iOS では true 必須
        applicationServerKey: urlBase64ToUint8Array(key),
    });

    await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subscription),
    });

    pushBtn.textContent = "🔔 通知はオンです";
    pushBtn.disabled = true;
}

if ("Notification" in window && "PushManager" in window) {
    pushBtn.hidden = false;
    if (Notification.permission === "granted") {
        pushBtn.textContent = "🔔 通知はオンです";
        pushBtn.disabled = true;
    }
    pushBtn.addEventListener("click", enablePush);
}

// プッシュから開かれたときの案内
// （iOS は通知タップで外部サイトへ飛べないため、ここでリンクを出す）
if (new URLSearchParams(location.search).get("from") === "push") {
    if (navigator.clearAppBadge) navigator.clearAppBadge();
    const box = el("div", "alert");
    box.innerHTML =
        '📚 予約本が届いています &nbsp;'
        + '<a href="https://www1.gifu-lib.jp/winj/opac/login.do?lang=ja&dispatch=/opac/mylibrary.do&every=1"'
        + ' target="_blank" rel="noopener noreferrer">メディコスのマイページを開く ↗</a>';
    resultsArea.prepend(box);
}
```

CSS（`app.css` に追記）：

```css
.btn-ghost {
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.22);
    color: var(--text);
    font-weight: 700;
}
.btn-ghost:hover { background: rgba(255, 255, 255, 0.18); }
.btn-ghost:disabled { opacity: 0.55; cursor: default; }
```

- [ ] 完了

---

## A-8. 実機で確認する（ここが本番）

> **シミュレータや Mac のブラウザでは検証できません。** 必ず実機で。

1. サーバーを起動
   ```bash
   .venv/bin/python run.py
   ```
2. iPhone で `https://monetmacbook-air.tail63c7e9.ts.net` を Safari で開く
3. 一度アイコンを**削除してから**「ホーム画面に追加」し直す（SWを新しくするため）
4. ホーム画面のアイコンから開く
5. **「🔔 通知をオンにする」をタップ** → 許可ダイアログ → 許可
6. Mac から送信テスト
   ```bash
   curl -X POST http://127.0.0.1:8000/api/push/test
   ```

チェック項目：

- [ ] iPhone に通知バナーが出た
- [ ] **アイコンに「1」が付いた**
- [ ] 通知をタップするとアプリが開き、「予約本が届いています」の案内が出た
- [ ] 案内のリンクからメディコスのマイページが開いた
- [ ] アプリを開いたらバッジが消えた

**🎉 ここまでで Laravel の予習は完了です。** 残りは実用化とデプロイ。

---

# Phase B — 公開に耐える形にする

> ⚠️ **ここを飛ばして Phase C をやると、URLを知っている人が誰でも開ける状態になります。**
> 検索履歴も見え、図書館サイトへのアクセスを他人に肩代わりすることになります。

## B-1. 認証をかける

`book_search_app/auth.py` を新規作成：

```python
"""単一ユーザー向けの簡易ログイン。

PWA ではブラウザの Basic 認証ダイアログが扱いにくいため、
パスワード1つ + 署名付きCookie の形にしている。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

COOKIE_NAME = "bf_session"
MAX_AGE = 60 * 60 * 24 * 365  # 1年

PASSWORD = os.environ.get("BOOKFINDER_PASSWORD", "")
SECRET = os.environ.get("BOOKFINDER_SECRET", "").encode()

# 認証なしで通すパス（PWAのインストールに必要なので保護しない。中身も非機密）
PUBLIC_PATHS = frozenset({
    "/login", "/sw.js", "/manifest.webmanifest", "/offline.html", "/favicon.ico",
})
PUBLIC_PREFIXES = ("/static/icons/", "/static/css/", "/static/js/", "/static/images/")


def _sign(issued_at: str) -> str:
    return hmac.new(SECRET, issued_at.encode(), hashlib.sha256).hexdigest()


def make_cookie_value() -> str:
    issued_at = str(int(time.time()))
    return f"{issued_at}.{_sign(issued_at)}"


def is_valid(cookie: str | None) -> bool:
    if not cookie or "." not in cookie:
        return False
    issued_at, signature = cookie.rsplit(".", 1)
    if not hmac.compare_digest(_sign(issued_at), signature):
        return False
    try:
        return time.time() - int(issued_at) < MAX_AGE
    except ValueError:
        return False


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


async def require_login(request: Request, call_next):
    """未ログインならログイン画面へ送るミドルウェア。"""
    if not PASSWORD or is_public(request.url.path):
        return await call_next(request)

    if is_valid(request.cookies.get(COOKIE_NAME)):
        return await call_next(request)

    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "ログインが必要です"}, status_code=401)

    return RedirectResponse("/login", status_code=303)
```

`main.py` に追記：

```python
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from . import auth

app.middleware("http")(auth.require_login)


@app.get("/login", include_in_schema=False)
async def login_form() -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>ログイン — Book Finder</title>'
        '<style>body{margin:0;min-height:100vh;display:flex;align-items:center;'
        'justify-content:center;background:#0C0820;color:#F5F0E8;'
        'font-family:system-ui,-apple-system,sans-serif}'
        'form{display:flex;flex-direction:column;gap:1rem;width:min(20rem,80vw)}'
        'input,button{font-size:1rem;padding:.9rem 1.1rem;border-radius:14px;border:none}'
        'input{background:rgba(255,255,255,.08);color:#fff;'
        'border:1px solid rgba(255,255,255,.22)}'
        'button{background:linear-gradient(90deg,#C8933E,#E8B55A);'
        'color:#120A00;font-weight:900}</style>'
        '<form method="post" action="/login">'
        '<input type="password" name="password" placeholder="パスワード" '
        'autocomplete="current-password" autofocus>'
        '<button type="submit">ログイン</button></form>'
    )


@app.post("/login", include_in_schema=False)
async def login(password: str = Form(...)) -> RedirectResponse:
    import hmac as _hmac
    if not _hmac.compare_digest(password, auth.PASSWORD):
        return RedirectResponse("/login", status_code=303)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME, auth.make_cookie_value(),
        max_age=auth.MAX_AGE, httponly=True, samesite="lax", secure=True,
    )
    return response
```

パスワードを決めて環境変数に：

```bash
# 秘密鍵はランダムに生成する
.venv/bin/python -c "import secrets;print(secrets.token_hex(32))"
```

`run.py` を使うときは事前に export：

```bash
export BOOKFINDER_PASSWORD='好きなパスワード'
export BOOKFINDER_SECRET='上で生成した文字列'
.venv/bin/python run.py
```

- [ ] ログイン画面が出る
- [ ] 正しいパスワードで入れる
- [ ] **ログインしていない状態で `/manifest.webmanifest` と `/sw.js` が 200 で取れる**（PWAのインストールに必要）

> ⚠️ **ここが一番ハマるポイント。** manifest や sw.js まで認証で塞ぐと、
> PWA としてインストールできなくなります。`PUBLIC_PATHS` で通しているのはそのためです。

---

## B-2. 検索エンジンに載らないようにする

`main.py` に追記：

```python
from fastapi.responses import PlainTextResponse


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nDisallow: /\n")
```

`auth.py` の `PUBLIC_PATHS` に `"/robots.txt"` を足す。

- [ ] 完了

---

## B-3. デプロイ先に合わせる

`run.py` を環境変数対応に：

```python
parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
```

`logging_config.py` — クラウドではファイルに書いても消えるので、標準出力だけにする：

```python
if os.environ.get("K_SERVICE"):      # Cloud Run が自動でセットする環境変数
    root.addHandler(console)          # ファイルハンドラは付けない
    return
```

- [ ] 完了

---

## B-4. 検索履歴を localStorage に移す

Cloud Run はコンテナが消えるとファイルも消えます。
**履歴をブラウザ側に持てば、サーバーに状態を持たずに済み、キーワードが外に出ません。**

- `history.py` と `/api/history` を削除
- `app.js` で `localStorage.getItem("bf_history")` / `setItem` を読み書き
- `index.html` の履歴チップはサーバー描画をやめ、JS で描く

- [ ] 完了

---

# Phase C — Cloud Run へデプロイ

## C-1. Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY book_search_app ./book_search_app
COPY run.py .

CMD ["python", "run.py", "--host", "0.0.0.0"]
```

`.dockerignore`：

```
.venv
.git
docs
tests
tools
logs
book_search_app/data
__pycache__
```

- [ ] 完了

## C-2. 購読情報の保存先を変える

`push_subscriptions.json` はコンテナと一緒に消えます。**Firestore に移してください**（無料枠内）。
`push.py` の `_load` / `_save` だけを差し替えれば済む設計にしてあります。

- [ ] 完了

## C-3. デプロイ

```bash
gcloud run deploy book-finder --source . --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars "BOOKFINDER_PASSWORD=...,BOOKFINDER_SECRET=..."
```

> `--allow-unauthenticated` は「Google の認証を使わない」という意味です。
> **アプリ側の認証（B-1）は効いています。** ここを外すとスマホから使いにくくなります。

- [ ] デプロイできた
- [ ] **予算アラートを 0 円 / 100 円で設定した**

---

# Phase D — スマホで登録し直す

1. ホーム画面の古いアイコンを削除
2. Cloud Run の URL を Safari で開く → ログイン
3. ホーム画面に追加
4. アイコンから開いて「🔔 通知をオンにする」を再タップ

- [ ] 通知テストがまた通った

---

# Phase E — Gmail と繋ぐ

Google Apps Script（`script.google.com`）で新規プロジェクト：

```javascript
const NOTIFY_URL = "https://<Cloud RunのURL>/api/push/notify";
const TOKEN = "<長いランダム文字列>";

function checkLibraryMail() {
  const query = 'is:unread newer_than:7d (from:gifu-lib.jp OR from:kani-lib.jp)';
  const threads = GmailApp.search(query);
  if (threads.length === 0) return;

  UrlFetchApp.fetch(NOTIFY_URL, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ count: threads.length }),
    headers: { Authorization: "Bearer " + TOKEN },
    muteHttpExceptions: true,
  });
}
```

- [ ] トリガーを「時間主導型 / 15分おき」で設定した
- [ ] `/api/push/notify` を作った（`TOKEN` を検証して `push.send()` を呼ぶ）
- [ ] 実際に図書館からメールが来たとき通知が出た

> 差出人アドレスは実際のメールを見て調整してください。
> **該当メールが無ければ HTTP を叩かない**ので、GAS の無料枠（90分/日）に余裕で収まります。

---

# 付録1. Laravel との対応表

| ここでやったこと | Laravel での相当物 |
|---|---|
| `sw.js` の `push` / `notificationclick` | **まったく同じものをそのまま使う** |
| `app.js` の購読処理・`urlBase64ToUint8Array` | **まったく同じ** |
| `tools/make_vapid.py` | `php artisan webpush:vapid` |
| `push.py` の `add` / `remove` | `HasPushSubscriptions` trait + `push_subscriptions` テーブル |
| `push.py` の `send` | `Notification` + `WebPushChannel` / `WebPushMessage` |
| 404/410 で購読を削除 | `MessageSentReport` が自動でやる |
| `VAPID_SUBJECT` | `.env` の `VAPID_SUBJECT`（**同じく mailto: か HTTPS URL 必須**） |

パッケージ: `composer require laravel-notification-channels/webpush`

# 付録2. 詰まったときのチェックリスト

| 症状 | 原因 | 対処 |
|---|---|---|
| 許可ダイアログが出ない | クリックハンドラの外で呼んでいる | A-7 の形にする |
| ホーム画面から開かないと通知ボタンが出ない | iOS の仕様（Safari のタブでは Push API が無い） | 正常。追加してから |
| 数回通知したら届かなくなった | `showNotification` を呼ばない push を送った | 必ず表示する |
| Apple が 403 を返す | `VAPID_SUBJECT` が mailto: / HTTPS URL でない | 直す |
| Safari で購読できない | `applicationServerKey` が文字列のまま | `Uint8Array` に変換する |
| バッジが出ない | 通知が未許可 / ホーム画面追加していない | 両方が必要 |
| 通知タップで図書館サイトに飛ばない | iOS では別オリジンに飛べない | 自分のオリジンへ飛ばし、画面にリンクを出す |
| SW を直したのに反映されない | `VERSION` を上げていない | 上げる |
| PWA としてインストールできない | manifest / sw.js を認証で塞いだ | `PUBLIC_PATHS` に入れる |
