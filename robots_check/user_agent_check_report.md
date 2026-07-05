# User-Agent の robots.txt チェックレポート

## 調査日
2024年（実行日時）

## アプリで使用しているUser-Agent
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

---

## 調査結果サマリー

| サイト名 | robots.txt | User-Agent Disallow | パスDisallow | 判定 |
|---------|-----------|-------------------|------------|------|
| 岐阜市立図書館 | ❌ 存在しない | ✅ なし | N/A | ✅ OK |
| 可児市立図書館 | ✅ 存在 | ✅ なし | ⚠️ `/csp` | ⚠️ 要確認 |
| 三省堂書店 | ✅ 存在 | ✅ なし | ⚠️ 一部パス | ✅ OK |
| TSUTAYA | ❌ 存在しない | ✅ なし | N/A | ✅ OK |

---

## 詳細結果

### 1. 岐阜市立図書館

**ベースURL:** https://www1.gifu-lib.jp/

**robots.txt:**
- ❌ robots.txt は存在しません（404エラー）

**User-Agentチェック:**
- ✅ **User-Agent自体はDisallowされていません**
- robots.txtが存在しないため、User-Agentによる制限はありません

**判定:**
- ✅ **User-Agentの使用は問題ありません**
- ただし、利用規約の確認が必要です

---

### 2. 可児市立図書館

**ベースURL:** https://www.kani-lib.jp/

**robots.txt:**
```
User-agent: *
Disallow: /csp
```

**User-Agentチェック:**
- ✅ **User-Agent自体はDisallowされていません**
- User-Agent `*`（すべてのUser-Agent）のルールに一致
- ただし、`/csp`パスがDisallowされています

**判定:**
- ✅ **User-Agentの使用は問題ありません**
- ⚠️ ただし、スクレイピング対象URL（`/csp/opw/OPW/...`）がDisallowされているため、**パスの問題があります**

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

**User-Agentチェック:**
- ✅ **User-Agent自体はDisallowされていません**
- User-Agent `*`（すべてのUser-Agent）のルールに一致
- 一部のパス（詳細ページ、在庫リストページ）がDisallowされていますが、検索実行ページ（`BookSearchExec.action`）は許可されています

**判定:**
- ✅ **User-Agentの使用は問題ありません**
- ✅ スクレイピング対象URL（`BookSearchExec.action`）はDisallowされていないため、**問題ありません**

---

### 4. TSUTAYA（草叢BOOKS）

**ベースURL:** https://store-tsutaya.tsite.jp/

**robots.txt:**
- ❌ robots.txt は存在しません（404エラー）

**User-Agentチェック:**
- ✅ **User-Agent自体はDisallowされていません**
- robots.txtが存在しないため、User-Agentによる制限はありません

**判定:**
- ✅ **User-Agentの使用は問題ありません**
- ただし、利用規約の確認が必要です

---

## 最終判定

### ✅ User-Agentの使用に関する判定

**すべてのサイトで、使用しているUser-AgentはDisallowされていません。**

アプリで使用しているUser-Agent（`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`）は、どのサイトのrobots.txtでもDisallowされていません。

### ⚠️ ただし、以下の点に注意が必要です

1. **User-AgentがDisallowされていなくても、特定のパスがDisallowされている可能性があります**
   - 可児市立図書館: `/csp`パスがDisallowされているため、スクレイピング対象URLが禁止されています
   - 三省堂書店: 一部のパスがDisallowされていますが、検索実行ページは許可されています

2. **利用規約でスクレイピングが禁止されている可能性があります**
   - robots.txtは技術的なガイドラインであり、法的な許可ではありません
   - 各サイトの利用規約を必ず確認してください

3. **サーバーに過度な負荷をかけないよう、適切な間隔でアクセスしてください**
   - 現在のコードでは、リクエスト間に適切な間隔を空けているか確認が必要です

---

## 結論

**User-Agent自体の使用は問題ありませんが、パスレベルの制限があるサイトがあります。**

特に、**可児市立図書館**については、User-Agentは問題ありませんが、スクレイピング対象URL（`/csp/opw/OPW/...`）がrobots.txtでDisallowされているため、**スクレイピング自体が禁止されています**。

---

## 推奨される対応

1. **可児市立図書館**
   - User-Agentは問題ありませんが、パスがDisallowされているため、スクレイピングを停止する必要があります

2. **その他のサイト**
   - User-Agentの使用は問題ありません
   - ただし、利用規約の確認を推奨します

3. **全体的な注意事項**
   - robots.txtに準拠していても、利用規約で禁止されている場合は違反となります
   - サーバー負荷を考慮した適切なアクセス間隔を維持してください

