# 📚 書籍横断検索アプリ - 開発ガイド

## プロジェクト概要
岐阜市立図書館・可児市立図書館・三省堂（岐阜）・TSUTAYA（各務原）の **4つ** を一括検索できるWebアプリケーションです。
一度の検索で、4つの場所の在庫状況を同時に確認できます。

※ Amazonは「検索結果ページを開く」ためのリンク（別タブ）を提供します（Amazon側の情報を取得して解析はしません）。

## 公開範囲について（重要）
本プロジェクトは、各サイトの検索結果ページを取得して在庫状況を判定する処理（HTML取得／スクレイピング相当）を含みます。

特に民間企業サイト（例：書店等）は、利用規約で自動取得（スクレイピング）を禁止している可能性があり、Public（公開）で配布すると不特定多数の利用によってアクセスが増えたり、規約上の問題が発生するリスクが高まります。

そのため、本リポジトリは **個人利用を前提に Private（非公開）で運用することを推奨**します。

※ 本プロジェクトは学習・個人利用目的で作成しています。各サイトの利用規約を確認し、短時間の連続アクセスは避けてください。

## 使用技術・言語

### 言語
- **Python 3.9+**

### 主要ライブラリ
- **Streamlit**: WebアプリのUI作成
- **requests**: HTTPリクエスト（Webページの取得）
- **BeautifulSoup4**: HTMLの解析
- **urllib.parse**: URLのエンコード処理

### その他
- HTML/CSS: カスタムスタイリング

## 開発の流れ（順番）

### ステップ1: 環境準備
1. Pythonのインストール確認
   ```bash
   python3 --version
   ```

2. 必要なライブラリのインストール
   ```bash
   pip3 install streamlit requests beautifulsoup4
   ```

### ステップ2: 各サイトの調査
1. **ブラウザの開発者ツールで調査**
   - 検索フォームの送信先URLを確認
   - パラメータ名を確認（`txt_word`, `keyword` など）
   - GET/POSTのどちらを使っているか確認

2. **curlコマンドでテスト**
   ```bash
   curl "https://example.com/search?keyword=Python"
   ```
   - 実際にリクエストを送って、レスポンスを確認
   - セッションが必要かどうかを確認

### ステップ3: 基本構造の作成
1. Streamlitアプリの骨組み
   - `st.title()`, `st.text_input()`, `st.button()` でUI作成
   - 検索キーワードの入力とボタン配置

2. **基本的なコード構造**
   ```python
   import streamlit as st
   
   st.title("📚 書籍横断検索アプリ")
   keyword = st.text_input("キーワードを入力してください")
   
   if st.button("検索"):
       # 検索処理
       pass
   ```

### ステップ4: 在庫チェック機能の実装
1. **各サイトごとの関数を作成**
   - `check_gifu_lib(keyword)`: 岐阜市立図書館
   - `check_kani_lib(keyword)`: 可児市立図書館
   - `check_sanseido(keyword)`: 三省堂（岐阜）
   - `check_tsutaya(keyword)`: TSUTAYA（各務原）

2. **ポイント:**
   - `requests.Session()` を使ってCookieを保持（可児市立図書館など）
   - `User-Agent` ヘッダーを設定（403エラー回避）
   - HTMLから「在庫あり/なし」の判定文字列を探す
   - `try-except` でエラーハンドリング

3. **実装例（岐阜市立図書館）**
   ```python
   def check_gifu_lib(keyword):
       try:
           session = requests.Session()
           # セッション初期化
           session.get("https://www1.gifu-lib.jp/winj/opac/top.do")
           # 検索実行
           url = "https://www1.gifu-lib.jp/winj/opac/search-standard.do"
           params = {"txt_word": keyword, ...}
           res = session.get(url, params=params)
           # 判定
           if "該当する資料はありません" in res.text:
               return "❌ なし"
           else:
               return "✅ あり"
       except:
           return "⚠️ エラー"
   ```

### ステップ5: 検索結果ページへのリンク生成
1. **URLパラメータのエンコード**
   - `urllib.parse.quote()` で日本語をエンコード
   - `urllib.parse.urlencode()` で複数パラメータを結合

2. **リンクの表示**
   - `st.markdown()` でHTMLの `<a>` タグを生成
   - `target="_blank"` で別タブで開く設定
   - `rel="noopener noreferrer"` でセキュリティ対策

3. **実装例**
   ```python
   encoded_keyword = urllib.parse.quote(keyword)
   url = f"https://example.com/search?keyword={encoded_keyword}"
   st.markdown(f'<a href="{url}" target="_blank">結果を開く ↗</a>', unsafe_allow_html=True)
   ```

### ステップ6: UIの改善
1. **CSSでスタイリング**
   - `st.markdown()` で `<style>` タグを埋め込み
   - カードデザイン、ボタンの色、ホバー効果など

2. **検索履歴機能**
   - `st.session_state` で履歴を保存
   - 最大5件まで保持
   - 履歴ボタンで再検索可能

3. **実装例（検索履歴）**
   ```python
   if 'search_history' not in st.session_state:
       st.session_state.search_history = []
   
   def add_to_history(kw):
       if kw not in st.session_state.search_history:
           st.session_state.search_history.insert(0, kw)
           if len(st.session_state.search_history) > 5:
               st.session_state.search_history = st.session_state.search_history[:5]
   ```

## 重要なポイント・学び

### 1. Webスクレイピングの基本
- **User-Agentの設定**: サーバーが「ロボット」と判断してブロックしないように
  ```python
  headers = {"User-Agent": "Mozilla/5.0 ..."}
  ```
- **セッション管理**: `requests.Session()` でCookieを保持
  ```python
  session = requests.Session()
  session.get("初期化URL")  # Cookie取得
  session.get("検索URL")    # Cookie使用
  ```
- **エンコーディング**: 日本語のURLは必ずエンコード
  ```python
  urllib.parse.quote("吾輩は猫である")  # %E5%90%BE%E8%BC%9E...
  ```

### 2. サイトごとの違いへの対応
- **岐阜市立図書館**: セッション必須（`top.do` で初期化が必要）
  - セッションCookieがないと検索結果ページにアクセスできない
  - ブラウザで直接リンクを開く場合、既存のCookieがあれば動作する可能性がある
- **可児市立図書館**: セッション初期化が必要（`OPWSRCH1.CSP` にアクセス）
  - セッション初期化後に検索を実行しないと正確な結果が得られない
- **三省堂（岐阜）**: GETリクエストで直接アクセス可能
  - フルパラメータ（空のパラメータも含む）を送信する必要がある
- **TSUTAYA（各務原）**: 2段階（検索結果→商品特定→店舗在庫）
  - キーワード検索結果は複数候補になりやすいため、本プロジェクトでは **検索結果の1位を採用**して在庫ページ（各務原）を生成します
  - `workId` と `productKey(ISBN/JAN)` を取得して、`storeSearchKeyword=各務原` を付けた在庫ページを開きます

### 3. エラーハンドリング
- `try-except` でエラーをキャッチ
- タイムアウト設定（`timeout=10`）
- エラー時は「⚠️ エラー」と表示

### 4. Streamlitの特徴
- **セッションステート**: `st.session_state` でデータを保持（リロードしても消えない）
- **HTML埋め込み**: `st.markdown(..., unsafe_allow_html=True)` でカスタムHTML
- **コンポーネント**: `st.columns()` でレイアウト
- **ボタンスタイル**: CSSで `div.stButton > button` をカスタマイズ

## セットアップ方法

1. **リポジトリのクローン（またはファイルのダウンロード）**
   ```bash
   git clone <repository-url>
   cd "Book Research"
   ```

2. **依存関係のインストール**
   ```bash
   pip3 install streamlit requests beautifulsoup4
   ```

3. **アプリの起動**
   ```bash
   streamlit run book_search_app/app.py
   ```

4. **ブラウザで開く**
   - 表示されたURL（通常は `http://localhost:8501`）をブラウザで開く
   - ポートが競合する場合は `--server.port 8502` などで変更可能

## ファイル構成

```
Book Research/
├── book_search_app/
│   └── app.py          # メインアプリケーション
├── README.md            # このファイル
└── (その他のテストファイル)
```

## 使い方

1. アプリを起動（`streamlit run book_search_app/app.py`）
2. ブラウザで表示されたURLを開く
3. 検索キーワードを入力（例: "Python", "吾輩は猫である"）
4. 「📚 図書館・書店を検索」ボタンをクリック
5. 4つのサイトの在庫状況が表示される
   - ✅ あり / ⭕️ 在庫あり: 在庫がある
   - ❌ なし: 在庫がない
   - ⚠️ 貸出中: 貸出中だが所蔵あり
6. 「結果を開く ↗」ボタンで各サイトの検索結果ページを別タブで開く
7. 「📦 Amazonで本を探す ↗」でAmazonの検索結果ページを別タブで開く
8. 検索履歴から過去の検索を再実行可能

## トラブルシューティング

### エラーが出る場合
- **`ModuleNotFoundError`**: 必要なライブラリがインストールされていない
  ```bash
  pip3 install streamlit requests beautifulsoup4
  ```

- **`streamlit: command not found`**: Streamlitがインストールされていない、またはパスが通っていない
  ```bash
  python3 -m streamlit run book_search_app/app.py
  ```

### 検索結果が正しく表示されない場合
- サイトのHTML構造が変更された可能性
- 判定文字列（「該当する資料はありません」など）を確認
- セッション初期化が必要なサイトで、初期化処理が正しく実行されているか確認

### リンクが開かない場合
- ブラウザのポップアップブロックを確認
- `target="_blank"` が正しく設定されているか確認
- `rel="noopener noreferrer"` が設定されているか確認

### ポートが既に使用されている場合
```bash
# ポート8501を使用しているプロセスを終了
lsof -i :8501 | grep LISTEN | awk '{print $2}' | xargs kill -9

# または別のポートで起動
streamlit run book_search_app/app.py --server.port 8502
```

## 開発時のデバッグ方法

1. **curlコマンドで直接テスト**
   ```bash
   curl -L "https://www1.gifu-lib.jp/winj/opac/search-standard.do?txt_word=Python"
   ```

2. **Pythonスクリプトでテスト**
   - 一時的なテストファイル（`test_gifu.py` など）を作成
   - 関数を個別にテスト

3. **Streamlitのコンソール出力を確認**
   - エラーメッセージが表示される
   - `print()` でデバッグ情報を出力

## 今後の拡張案

- [ ] 他の図書館・書店の追加
- [ ] 検索履歴の永続化（ファイル保存）
- [ ] 通知機能（在庫が入ったらメール）
- [ ] デプロイ（Streamlit Cloudなど）
- [ ] ログイン機能の追加（自動ログイン）
- [ ] 検索結果の詳細表示（件数、著者名など）

## 技術的な学び

### Webスクレイピングの注意点
- **robots.txt の確認**: サイトの利用規約を確認
- **リクエスト間隔**: サーバーに負荷をかけないよう適切な間隔を空ける
- **User-Agent**: 適切なUser-Agentを設定
- **エラーハンドリング**: ネットワークエラーやタイムアウトに対応

### Streamlitのベストプラクティス
- **セッションステート**: アプリの状態を保持
- **キャッシング**: `@st.cache_data` で重い処理をキャッシュ（今回は未使用）
- **レイアウト**: `st.columns()` でレスポンシブなレイアウト
- **カスタムCSS**: `st.markdown()` でスタイルを追加

## 参考資料

- [Streamlit公式ドキュメント](https://docs.streamlit.io/)
- [requests ライブラリ](https://requests.readthedocs.io/)
- [BeautifulSoup4 ドキュメント](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [urllib.parse ドキュメント](https://docs.python.org/3/library/urllib.parse.html)

## ライセンス

個人利用・学習目的での使用を想定しています。

## 作成者

学習用プロジェクトとして作成されました。

