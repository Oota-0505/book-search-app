# 📚 書籍横断検索アプリ - 開発ガイド

## プロジェクト概要
**メディコス**（岐阜市立図書館）・**ミライブ**（可児市立図書館）・**岐阜駅本屋**（三省堂）・**各務原BC**（草叢BOOKS）の **4つ** を一括検索できる Web アプリケーションです。
一度の検索で、4つの場所の在庫状況を同時に確認できます。

- **Amazon**: 検索結果ページを開くリンク（別タブ）を表示
- **マイページ**: メディコス・ミライブのログインページへのリンクを表示

## 使用技術
- **Python 3.9+**
- **Streamlit**: Web アプリフレームワーク
- **requests**: HTTP 通信
- **BeautifulSoup4**: HTML 解析（スクレイピング）

## 機能特徴
1. **横断検索**: 4つの図書館・書店サイトの在庫を一括チェック
2. **検索履歴**: 直近5件の履歴を保存
3. **マイページリンク**: メディコス・ミライブのログインへワンクリックで遷移
4. **Amazon リンク**: キーワードで Amazon の検索結果を開く
5. **リッチな UI**: カード型レイアウト、背景画像、レスポンシブ対応（スタイルは `static/css/`、画像は `static/images/` で管理）

## セットアップ方法

1. **リポジトリのクローン**
   ```bash
   git clone <repository-url>
   cd "Book Research"
   ```

2. **依存関係のインストール**
   ```bash
   pip3 install -r requirements.txt
   # または
   pip3 install streamlit requests beautifulsoup4
   ```

3. **アプリの起動**
   ```bash
   streamlit run book_search_app/app.py
   ```

4. **利用開始**
   ブラウザで `http://localhost:8501` を開いてください。

## ファイル構成
```
Book Research/
├── book_search_app/
│   ├── app.py              # メインアプリケーション
│   └── static/             # 静的アセット（画像・CSS）
│       ├── images/         # 背景・カード用画像
│       │   ├── 松本十畳.jpg
│       │   ├── メディコス.webp
│       │   ├── ミライブ.webp
│       │   ├── 岐阜駅本屋.png
│       │   └── 各務原BC.jpg
│       └── css/            # スタイルシート（分割）
│           ├── variables.css
│           ├── layout.css
│           ├── forms.css
│           ├── cards.css
│           ├── loading.css
│           └── responsive.css
├── docs/
│   ├── README.md           # このファイル（開発ガイド）
│   └── requirements.md     # 要件定義書
├── robots_check/          # robots.txt チェック用ユーティリティ
├── requirements.txt        # 依存ライブラリ
└── .streamlit/             # Streamlit 設定
```

## 注意事項
- **スクレイピングについて**: 各サイトの検索結果ページを取得して解析しています。個人利用・学習目的での使用を前提とし、短時間の大量アクセスは避けてください。

## ライセンス
個人利用・学習目的での使用を想定しています。
