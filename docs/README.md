# 📚 書籍横断検索アプリ - 開発ガイド

## プロジェクト概要
岐阜市立図書館・可児市立図書館・岐阜駅本屋・草叢BOOKSの **4つ** を一括検索できるWebアプリケーションです。
一度の検索で、4つの場所の在庫状況を同時に確認できます。また、検索結果の下には **Google Books API** を利用して、本の概要（表紙画像・あらすじ等）を自動的に表示します。

※ Amazonは「検索結果ページを開く」ためのリンク（別タブ）を提供します。

## 使用技術
- **Python 3.9+**
- **Streamlit**: Webアプリフレームワーク
- **requests**: HTTP通信
- **BeautifulSoup4**: HTML解析（スクレイピング）

## 機能特徴
1. **横断検索**: 4つの図書館・書店サイトの在庫を一括チェック
2. **本の概要表示**: Google Books APIから書誌情報（表紙・著者・要約）を取得して表示（無料・登録不要）
3. **検索履歴**: 直近5件の履歴を保存
4. **リッチなUI**: 見やすいカード型レイアウト、レスポンシブ対応

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
│   └── app.py          # メインアプリケーション
├── docs/
│   ├── README.md       # このファイル（開発ガイド）
│   └── requirements.md # 要件定義書
├── requirements.txt     # 依存ライブラリ
└── runtime.txt         # ランタイム設定
```

## 注意事項
- **スクレイピングについて**: 各サイトの検索結果ページを取得して解析しています。個人利用・学習目的での使用を前提とし、短時間の大量アクセスは避けてください。
- **Google Books API**: 無料枠の範囲内で利用しています。

## ライセンス
個人利用・学習目的での使用を想定しています。
