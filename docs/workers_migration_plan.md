# Cloudflare Workers 移行設計（改訂版）

- 作成: 2026-09-05
- 決定: デプロイ先を **Cloudflare Workers（Python）** とする
- 状態: **設計のみ。実装は未着手**
- 差し替え対象: [`hosting_proposal.md`](hosting_proposal.md) の「Cloud Run 本命」案

---

## 0. なぜ Cloud Run から変えたのか

| | Cloud Run | **Cloudflare Workers** |
|---|---|---|
| 費用 | 無料枠内 | 無料（10万リクエスト/日） |
| **カード登録** | **必要** | **不要** |
| コールドスタート | 数秒 | **ミリ秒** |
| 使い慣れ | なし | **あり** |
| Artifact Registry の保管料 | 0.5GB超で課金（実例: 月1,300円） | なし |

起動速度を 6.5秒 → 0.6秒 にしたのに、コールドスタートで数秒待たされては本末転倒。
カード登録が要らない点も、当初の希望に合致する。

---

## 1. ⚠️ 最大の制約: CPU 10ms

Workers 無料プランは **1リクエストあたり CPU 時間 10ms** が上限。
**ネットワークの待ち時間は含まれない**が、HTML の解析時間は含まれる。

現行コードで実測した結果、**そのままでは超過する**ことが分かった。

| 処理 | CPU時間（ネイティブ CPython） |
|---|---|
| **各務原BC: BeautifulSoup 解析**（51KB） | **11.047 ms** ← 単体で既に超過 |
| 文字コード自動判定（`apparent_encoding`） | 1.77 ms |
| 岐阜駅本屋: 正規表現スキャン（16KB） | 0.02 ms |
| メディコス: 文字列検索（37KB） | 0.04 ms |
| **合計** | **13.13 ms** |

Pyodide（WASM）はネイティブの2〜5倍遅いため、推定 **26〜66ms**。上限の3〜7倍。

### 解決策: BeautifulSoup を捨てる

BeautifulSoup は**1か所でしか使っていない**（各務原BCの `workId` 抽出）。
やっていることは「`/search/result/select?` を含む最初の `<a>` から `workId` を取る」だけで、
正規表現1本で置き換えられる。

```python
# 現行（11.047 ms）
soup = BeautifulSoup(html, "html.parser")
anchor = soup.find("a", href=re.compile(r"/search/result/select\?"))
match = _WORK_ID_RE.search(anchor.get("href") or "")

# 改修後（0.014 ms・結果は完全に一致することを実測で確認）
_WORK_ID_RE = re.compile(r'href="[^"]*/search/result/select\?[^"]*workId=(\d+)')
match = _WORK_ID_RE.search(html)
```

あわせて `res.encoding = res.apparent_encoding`（統計的な文字コード推定）もやめ、
サイトごとに既知の文字コードを固定する。

### 改修後の見込み

| | CPU時間 |
|---|---|
| 改修後（ネイティブ実測） | **0.074 ms** |
| Pyodide 想定（2〜5倍） | **0.15〜0.37 ms** |
| Workers 無料プランの上限 | 10.00 ms |

**余裕をもって収まる。** 副産物として BeautifulSoup4 を依存から外せる。

> ⚠️ **ただし1点だけ未検証。** Pyodide 自体の起動に使う CPU が
> リクエストの10msに算入されるかが不明。Cloudflare はランタイムを
> スナップショットして高速化していると説明しているが、断定はできない。
> → **§5 のとおり、まず hello world を1本デプロイして実測すること。**

---

## 2. ほかに必要な書き換え

| 箇所 | 現行 | Workers 版 | 理由 |
|---|---|---|---|
| HTTP クライアント | `requests` | **`httpx`（async）** | Workers に生の TCP が無く、`fetch` 経由になるため `requests` は動かない |
| 並列実行 | `ThreadPoolExecutor` | **`asyncio.gather`** | Workers にスレッドが無い |
| HTML 解析 | `BeautifulSoup` | **正規表現** | §1 のCPU制限 |
| 文字コード | `apparent_encoding` | **サイトごとに固定** | 同上 |
| 検索履歴 | サーバー上の JSON | **localStorage** | Workers にファイルシステムが無い（元々そうする予定） |
| プッシュ購読の保存 | JSON ファイル | **Workers KV** | 同上 |
| ログ | ファイル + 標準出力 | **標準出力のみ** | `wrangler tail` で見る |
| 静的ファイル | `StaticFiles` | **Workers Static Assets** | CDN 配信になり、無料かつ高速 |

### providers.py の書き換えイメージ

```python
# 現行
def check_sanseido(keyword: str) -> tuple[models.BookStatus, str]:
    res = _session().get(URL, params=..., timeout=TIMEOUT_SHORT)
    res.encoding = res.apparent_encoding
    ...

# Workers 版
async def check_sanseido(client: httpx.AsyncClient, keyword: str) -> tuple[models.BookStatus, str]:
    res = await client.get(URL, params=..., timeout=TIMEOUT_SHORT)
    text = res.content.decode("utf-8", errors="replace")   # 文字コードは固定
    ...
```

### search.py の書き換えイメージ

```python
async def search(keyword: str) -> tuple[list[models.SiteResult], bool]:
    async with httpx.AsyncClient(headers=HEADERS) as client:
        results = await asyncio.gather(
            *(_check_one(client, site, keyword) for site in SITES)
        )
    ...
```

`_check_one` の「例外を握って他サイトを巻き込まない」構造はそのまま使える
（`asyncio.gather(..., return_exceptions=True)` でも良いが、
サイトごとに握るほうが `link` フォールバックを返せる）。

---

## 3. 認証をどうするか

公開する以上、認証は必須（理由は [`hosting_proposal.md`](hosting_proposal.md) §1）。
Cloudflare なら2つの選択肢がある。

| | Cloudflare Access | アプリ自前のCookieログイン |
|---|---|---|
| 費用 | 無料（50ユーザーまで） | 無料 |
| ログイン方法 | Google アカウント等 | パスワード1つ |
| 実装量 | ほぼゼロ（管理画面で設定） | 50行ほど |
| **PWAとの相性** | **未検証**（OAuthリダイレクトがSWの登録を妨げないか要確認） | **実績あり** |

**推奨: まず自前のCookieログイン**（[`implementation_plan.md`](implementation_plan.md) B-1 の実装をそのまま使う）。
PWA として確実に動くことを優先する。Access は動作確認できたら乗り換えれば良い。

> ⚠️ どちらの場合も、`/manifest.webmanifest` `/sw.js` `/offline.html` `/static/icons/*` は
> **認証なしで通すこと。** ここを塞ぐと PWA としてインストールできなくなる。
> Access を使う場合も、これらのパスに Bypass ポリシーを設定する。

---

## 4. プッシュ通知をどう送るか

**⚠️ ここは Cloud Run 案から設計が変わる。**

`pywebpush` は `cryptography`（C拡張）に依存しており、
Pyodide で動くかが不透明。VAPID の ES256 署名と本文の暗号化が必要なため、
これが動かないとプッシュを送れない。

### 提案: プッシュ送信だけ JavaScript の Worker にする

```
[Book Finder 本体]      Python Worker  … 検索・画面
[プッシュ送信]          JS Worker      … Web Crypto API が標準で使える
[Gmail監視]             Apps Script    … 15分ごとにGmailを検索
[購読情報]              Workers KV     … 両方から読める
```

JavaScript なら Web Crypto API が標準搭載で、ES256 署名も ECDH 暗号化も
追加ライブラリなしで書ける。**むしろ Python より素直**。

さらに **Cron Triggers** を使えば Apps Script すら不要にできる可能性がある
（Worker から Gmail API を直接叩く）。ただし OAuth の管理が増えるので、
まずは Apps Script で作るほうが早い。

> **学習面での補足**: 「プッシュの送信側は言語を選ばない」ことが、
> ここでも確認できる。ブラウザ側（Service Worker・購読処理）は
> Python 版でも JS 版でも Laravel 版でも**まったく同じ**。

---

## 5. 進め方（重要: いきなり全部移植しない）

未検証点（Pyodide の起動CPU）があるため、**小さく確かめてから進む**。

| # | やること | 目的 | 中止条件 |
|---|---|---|---|
| **0** | **hello world の Python Worker を1本デプロイ** | **Pyodide の起動CPUが10msに収まるか実測** | ここで超過するなら Workers を諦め、Cloud Run に戻る |
| 1 | `providers.py` の BeautifulSoup を正規表現へ、文字コードを固定 | CPU削減。**ローカルで先にやってテストを通す** | — |
| 2 | `requests` → `httpx`、`ThreadPoolExecutor` → `asyncio.gather` | Workers 対応。これもローカルで完結できる | — |
| 3 | 検索履歴を localStorage へ | 状態をサーバーに持たない | — |
| 4 | 自前Cookieログインを実装 | 公開に備える | — |
| 5 | `wrangler` で Workers へデプロイ | Mac 不要になる | — |
| 6 | スマホで再登録 → プッシュ実装（Phase A） | — | — |

**手順1〜4はすべてローカルで完結し、今のテスト22件で検証できる。**
Workers に触るのは手順0と5だけ。

### 手順0 の具体的なやり方

```bash
npm install -g wrangler
wrangler login
mkdir /tmp/pyworker && cd /tmp/pyworker
# 最小のPython Workerを作り、CPU時間をログで確認する
wrangler deploy
wrangler tail   # ← ここでCPU時間を観測する
```

---

## 6. この設計で変わらないこと

- **スクレイピングポリシーは一切変わらない**（robots.txt遵守・キャッシュ・UA明示）
- ミライブは引き続きリンク提示のみ
- 公開する以上、認証は必須という判断も変わらない
- PWA の実装（manifest / sw.js / アイコン）はそのまま使える

---

## 参考にした情報源

- [Pricing · Cloudflare Workers docs](https://developers.cloudflare.com/workers/platform/pricing/)
- [Write Cloudflare Workers in Python · Cloudflare Workers docs](https://developers.cloudflare.com/workers/languages/python/)
- [Python packages supported in Cloudflare Workers](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Python Workers redux: fast cold starts, packages, and a uv-first workflow | Cloudflare Blog](https://blog.cloudflare.com/python-workers-advancements/)
- [Cloudflare Workers Free Tier 2026: Limits, Pricing & What Changed](https://agentdeals.dev/vendor/cloudflare-workers)
