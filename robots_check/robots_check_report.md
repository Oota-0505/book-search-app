# robots.txt および meta robots タグ 確認レポート

## 調査日
2024年（実行日時）

## 調査対象サイト
1. 岐阜市立図書館
2. 可児市立図書館
3. 三省堂書店（岐阜駅本屋）
4. TSUTAYA（草叢BOOKS）

---

## 調査結果サマリー

| サイト名 | robots.txt | meta robots | スクレイピング許可状況 | 判定 |
|---------|-----------|-------------|---------------------|------|
| 岐阜市立図書館 | ❌ 存在しない | ⚠️ 一部noindex | ⚠️ **要確認** | ❌ |
| 可児市立図書館 | ✅ 存在 | ❌ 制限なし | ❌ **禁止** | ❌ |
| 三省堂書店 | ✅ 存在 | ✅ 制限なし | ✅ **許可** | ✅ |
| TSUTAYA | ❌ 存在しない | ✅ 制限なし | ✅ **許可** | ✅ |

---

## 詳細結果

### 1. 岐阜市立図書館

**ベースURL:** https://www1.gifu-lib.jp/

**robots.txt:**
- ❌ robots.txt は存在しません（404エラー）

**meta robotsタグ:**
- ⚠️ トップページ（`/winj/opac/top.do`）に `noindex` が設定されています
- ✅ 検索ページ（`/winj/opac/search-standard.do`）には制限なし

**スクレイピング対象URL:**
- `https://www1.gifu-lib.jp/winj/opac/top.do` - ⚠️ noindex設定あり
- `https://www1.gifu-lib.jp/winj/opac/search-standard.do` - ✅ 制限なし

**判定:**
- ❌ **スクレイピングは推奨されません**
- トップページに`noindex`が設定されているため、サイト運営者はインデックスを望んでいない可能性があります
- 検索ページ自体には制限がありませんが、利用規約の確認が必要です

---

### 2. 可児市立図書館

**ベースURL:** https://www.kani-lib.jp/

**robots.txt:**
```
User-agent: *
Disallow: /csp
```

**解析結果:**
- User-Agent: `*` (すべてのクローラー)
- Disallow: `/csp` パスが禁止されています
- Allow: なし
- Crawl-delay: なし

**meta robotsタグ:**
- ✅ 制限なし

**スクレイピング対象URL:**
- ❌ `https://www.kani-lib.jp/csp/opw/OPW/OPWSRCH1.CSP` - **禁止**（`/csp`パスがDisallow）
- ❌ `https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP` - **禁止**（`/csp`パスがDisallow）

**判定:**
- ❌ **スクレイピングは禁止されています**
- robots.txtで`/csp`パスが明示的にDisallowされているため、このサイトへのスクレイピングは**robots.txtに違反**します

---

### 3. 三省堂書店（岐阜駅本屋）

**ベースURL:** https://www.books-sanseido.jp/

**robots.txt:**
```
user-Agent: *
Disallow: /booksearch/BookSearchDetail.action*
Disallow: /booksearch/EBookSearchDetail.action*
Disallow: /booksearch/BookStockList.action*
```

**解析結果:**
- User-Agent: `*` (すべてのクローラー)
- Disallow: 詳細ページと在庫リストページが禁止
- Allow: なし
- Crawl-delay: なし

**meta robotsタグ:**
- ✅ 制限なし

**スクレイピング対象URL:**
- ✅ `https://www.books-sanseido.jp/booksearch/BookSearchExec.action` - **許可**（Disallowされていない）

**判定:**
- ✅ **スクレイピングは許可されています**
- 検索実行ページ（`BookSearchExec.action`）はDisallowされていないため、robots.txtに準拠しています

---

### 4. TSUTAYA（草叢BOOKS）

**ベースURL:** https://store-tsutaya.tsite.jp/

**robots.txt:**
- ❌ robots.txt は存在しません（404エラー）

**meta robotsタグ:**
- ✅ 制限なし

**スクレイピング対象URL:**
- ✅ `https://store-tsutaya.tsite.jp/search/result/select` - 制限なし
- ✅ `https://store-tsutaya.tsite.jp/search/result/` - 制限なし
- ✅ `https://store-tsutaya.tsite.jp/search/result/stock/result` - 制限なし

**判定:**
- ✅ **スクレイピングは技術的には可能です**
- robots.txtが存在しないため、技術的な制限はありません
- ただし、利用規約の確認が必要です

---

## 最終判定

### ❌ スクレイピングが制限されているサイト

1. **可児市立図書館** - robots.txtで`/csp`パスがDisallowされているため、**明確に禁止**
2. **岐阜市立図書館** - トップページに`noindex`が設定されており、**推奨されない**

### ✅ スクレイピングが許可されているサイト

1. **三省堂書店（岐阜駅本屋）** - robots.txtで許可されている
2. **TSUTAYA（草叢BOOKS）** - robots.txtが存在せず、制限なし

---

## 推奨される対応

### 1. 即座に対応すべき事項

- ❌ **可児市立図書館へのスクレイピングを停止する**
  - robots.txtで明確に禁止されているため、違反行為となります
  - サイト運営者に連絡して許可を得るか、スクレイピング機能を削除してください

### 2. 確認が必要な事項

- ⚠️ **岐阜市立図書館**
  - 利用規約を確認し、スクレイピングが許可されているか確認
  - 可能であれば、サイト運営者に連絡して許可を得る

### 3. 継続可能な事項

- ✅ **三省堂書店（岐阜駅本屋）** - robots.txtに準拠しているため、継続可能
- ✅ **TSUTAYA（草叢BOOKS）** - 技術的な制限はないが、利用規約の確認を推奨

---

## 重要な注意事項

1. **robots.txtは技術的なガイドラインであり、法的な許可ではありません**
   - robots.txtに準拠していても、利用規約で禁止されている場合は違反となります
   - 各サイトの利用規約を必ず確認してください

2. **サーバー負荷への配慮**
   - スクレイピングを行う際は、適切な間隔（例：1秒以上）を空けてアクセスしてください
   - 過度なアクセスは、サーバーに負荷をかける可能性があります

3. **データの利用目的**
   - 取得したデータの利用目的が、各サイトの利用規約に準拠しているか確認してください
   - 個人利用・学習目的での使用を想定している場合でも、規約を確認してください

4. **公式APIの利用**
   - 可能であれば、各サイトが提供する公式APIを利用することを推奨します
   - APIが提供されている場合は、スクレイピングよりもAPIの利用が適切です

---

## 結論

現在のアプリケーションは、**可児市立図書館へのスクレイピングがrobots.txtに違反**しています。
**岐阜市立図書館についても、`noindex`設定があるため、利用規約の確認が必要**です。

**推奨される対応:**
1. 可児市立図書館のスクレイピング機能を削除または無効化する
2. 岐阜市立図書館の利用規約を確認し、必要に応じて運営者に連絡する
3. 三省堂書店とTSUTAYAについては、利用規約を確認した上で継続可能

