# 📚 書籍横断検索アプリ「Book Finder」— 開発ガイド

## プロジェクト概要
**メディコス**（岐阜市立図書館）・**ミライブ**（可児市立図書館）・**岐阜駅本屋**（三省堂）・**各務原BC**（草叢BOOKS）の **4つ** を一括検索できる Web アプリケーションです。
一度の検索で、4つの場所の在庫状況を同時に確認できます。

> **Note**: ミライブ（可児市立図書館）は、同館の robots.txt が検索パスへの自動アクセスを
> 禁止しているため在庫の自動判定を行わず、検索結果ページへのリンク提示のみとしています
> （詳細は下記「スクレイピングポリシー」参照）。

- **Amazon**: 検索結果ページを開くリンク（別タブ）を表示
- **マイページ**: メディコス・ミライブのログインページへのリンクを表示
- **PWA**: ホーム画面に追加してアプリのように使えます（HTTPS環境が必要）

## 使用技術
- **Python 3.11+**
- **FastAPI** + **uvicorn**: Web フレームワーク／ASGI サーバー
- **Jinja2**: HTML テンプレート
- **requests**: HTTP 通信
- **BeautifulSoup4**: HTML 解析

> **2026-09 に Streamlit から FastAPI へ移行しました。**
> Streamlit は起動のたびに 1.75MB の JS バンドルと WebSocket 接続が必要で、
> スマホから開くと画面が出るまで実測 6.5 秒かかっていました。
> 素の HTML を返す構成に変えたことで **0.56 秒（サーバー起動）＋ 73ms（描画）** になっています。
> 経緯と数値は [`migration_report.md`](migration_report.md) を参照。

## セットアップ方法

1. **リポジトリのクローン**
   ```bash
   git clone <repository-url>
   cd "Book Research"
   ```

2. **仮想環境の作成と依存関係のインストール**
   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

3. **アプリの起動**
   ```bash
   .venv/bin/python run.py
   ```

4. **利用開始**
   ブラウザで `http://127.0.0.1:8000` を開いてください。

### よく使うコマンド

```bash
.venv/bin/python run.py --reload          # 保存するたび自動再起動（開発用）
.venv/bin/python run.py --host 0.0.0.0    # 同じWi-Fi内のスマホから開く
.venv/bin/python -m pytest tests/ -q      # テスト
.venv/bin/python tools/verify_pwa.py      # 実ChromeでPWAを検証
.venv/bin/python tools/make_icons.py      # PWAアイコンを再生成
```

## ファイル構成
```
Book Research/
├── run.py                      # 起動スクリプト
├── book_search_app/
│   ├── main.py                 # FastAPI アプリ・ルーティング
│   ├── config.py               # 定数・パス・設定
│   ├── models.py               # BookStatus / SiteResult
│   ├── providers.py            # 各サイトの在庫チェック（唯一、外部へ通信する層）
│   ├── search.py               # 並列検索 + TTLキャッシュ
│   ├── history.py              # 検索履歴の永続化
│   ├── logging_config.py       # ロギング設定
│   ├── templates/
│   │   └── index.html          # 画面（1ページのみ）
│   └── static/
│       ├── css/app.css
│       ├── js/app.js
│       ├── images/*.webp       # 背景・カード用画像
│       ├── icons/              # PWA アイコン
│       ├── manifest.webmanifest
│       ├── sw.js               # Service Worker（/sw.js として配信）
│       └── offline.html
├── tools/
│   ├── make_icons.py           # PWA アイコン生成
│   └── verify_pwa.py           # 実ブラウザでのPWA検証
├── tests/                      # pytest
├── docs/
├── robots_check/               # robots.txt チェック用ユーティリティ
└── requirements.txt
```

## PWA について

[`PWA_GUIDE`](../../Laravel%20Youtube/EthioPick/docs/PWA_GUIDE.md) の仕様に沿って実装しています。

| 項目 | 実装 |
|---|---|
| manifest | `/manifest.webmanifest`（`application/manifest+json` で配信） |
| Service Worker | `/sw.js`（ルート直下 + `Service-Worker-Allowed: /` + `Cache-Control: no-cache`） |
| オフライン画面 | `/offline.html`（外部リソースを一切読み込まない） |
| アイコン | 192 / 512 / maskable 192 / maskable 512 / apple-touch-icon 180（すべて不透明） |

### キャッシュ方針

| 対象 | 方針 | 理由 |
|---|---|---|
| `/static/…`、アイコン | cache-first | 内容が変わっても `?v=` が変わるので安全 |
| HTML（画面遷移） | network-first、失敗時のみオフライン画面 | 最新の状態を守る |
| `/api/…` | **キャッシュしない** | 在庫は時間で変わる。古い結果を見せる害のほうが大きい |
| GET 以外・別ドメイン | 一切触らない | — |

> `sw.js` を編集したら **`VERSION` を必ず上げてください**。上げ忘れると端末に古いSWが残り続けます。

### スマホでホーム画面に追加する

**Service Worker は HTTPS でしか動きません**（`http://localhost` だけが例外）。
`http://192.168.x.x:8000` のような LAN 内アクセスでは登録されません。

- **HTTPSなし**でも「ホーム画面に追加」自体はでき、アイコンと全画面表示は効きます。
- **オフライン動作**を効かせるには HTTPS が必要です。手元では Tailscale が使えます:
  ```bash
  tailscale serve --bg 8000
  ```
- ただし **Tailscale 方式は Mac が起動している必要があります**。
  外出先でスマホ単独で使うためのホスティング案は
  [`hosting_proposal.md`](hosting_proposal.md) にまとめています。

## スクレイピングポリシー

本アプリは各サイトの検索結果ページを取得して解析します。公開Webサイトへの自動アクセスを伴うため、以下の方針を守って実装・運用しています。

1. **robots.txt の遵守**
   - 対象4サイトの robots.txt を事前調査し、遵守しています（調査用ツール: `robots_check/`）。
   - **ミライブ（可児市立図書館）**は robots.txt が検索パス `/csp` 配下を Disallow しており、
     2026年5月には運営側が「サーバ負荷軽減」の注記を追加したため、
     **2026年7月に在庫の自動判定を停止**し、リンク提示のみに変更しました。
   - 三省堂は robots.txt で許可されている検索実行ページのみ使用し、Disallow 対象の
     詳細ページ・在庫リストページには一切アクセスしません。
2. **サーバー負荷の抑制**
   - 検索結果を **10分間キャッシュ**し、同一キーワードの再検索でサイトへ再アクセスしません。
   - アクセスは利用者の手動検索1回につき各サイト1〜3リクエストのみ。バックグラウンド巡回・定期実行は行いません。
   - Service Worker も `/api/` を一切キャッシュしませんが、逆に**先読みや自動再取得も行いません**。
3. **透明性**
   - User-Agent にアプリ識別子（`BookFinder/1.0 (personal-use)`）を付与しています。
4. **利用目的の限定**
   - 個人利用・学習目的専用です。**運用サービスとしての一般公開や商用利用は行いません**
     （各サイトの利用規約・サイトポリシー上、許諾なしの商用利用はできません）。
   - 公開・収益化する場合の合法的な構成（カーリル図書館API への移行等）は
     [`scraping_monetization_report.md`](scraping_monetization_report.md) にまとめています。

## ライセンス
個人利用・学習目的での使用を想定しています。
