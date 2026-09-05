# 予約本の到着をプッシュ通知＋アイコンバッジで受け取れるか（調査レポート）

- 作成: 2026-09-05
- 状態: **調査のみ。実装は未着手**
- 調べたこと: 岐阜市立図書館（メディコス）・可児市立図書館（ミライブ）の予約本到着を、
  Gmail を起点に Book Finder のプッシュ通知として受け取り、アプリアイコンに件数バッジを出せるか

---

## 0. 結論

**技術的には可能です。** 必要な部品はすべて iOS で動きます。

ただし **「Mac の電源が入っていないと通知が飛ばない」**という前提がつきます。
これは [`hosting_proposal.md`](hosting_proposal.md) と同じ根っこの問題です。

| 要素 | 可否 | 根拠 |
|---|---|---|
| iPhone でプッシュ通知を受け取る | ✅ | iOS 16.4+ / ホーム画面追加済みのPWAで Push API が使える |
| アイコンに「1」「2」を出す | ✅ | Badging API が iOS 16.4+ で使える。**Service Worker の push イベントから更新できる** |
| Gmail の到着を検知する | ✅ | Gmail API / Google Apps Script。**自分のメールを読むだけ**なので図書館サイトには一切触れない |
| 常に通知が届く | ⚠️ | **送信側が常時起動している必要がある**。今の構成では Mac 依存 |

### 一番いいのは「ミライブでも使える」こと

見落とされがちな点ですが、この機能は**可児市立図書館のサーバーに一切アクセスしません**。
読むのは自分の Gmail だけです。

つまり、robots.txt を理由に**検索の自動判定は止めたままでも、
予約本の到着通知は普通に実装できます**。制約の外にある機能です。

---

## 1. 仕組み（全体像）

```
[図書館] --メール--> [自分のGmail]
                          |
                   ①到着を検知する人
                          |
                          v
                   ②プッシュを送る人  --VAPID署名--> [Appleのプッシュサーバー]
                                                            |
                                                            v
                                                    [iPhone のBook Finder]
                                                     ・通知を表示
                                                     ・アイコンにバッジ「2」
```

ポイントは、**②から先は Apple が配達してくれる**ことです。
iPhone が Mac と繋がっている必要はありません。Mac が必要なのは①②の瞬間だけです。

---

## 2. iOS 側の制約（ここを外すと動かない）

調べたなかで、**知らずに踏むと必ずハマる**ものを挙げます。

### ① ホーム画面に追加したPWAでしか動かない

Push API も Badging API も、**Safari のタブで開いている状態では使えません**。
「共有 → ホーム画面に追加」を経たアプリでのみ有効です。
→ すでに追加済みなので、この条件は**クリア済み**です。

### ② HTTPS が必須

→ Tailscale で HTTPS 化済みなので**クリア済み**です。

### ③ 通知許可は「指をタップした瞬間」にしか聞けない

`Notification.requestPermission()` をページ読み込み時や `setTimeout` の中で呼ぶと、
**iOS では黙って無視されます**。「通知をオンにする」ボタンを置いて、
そのクリックハンドラの中で呼ぶ必要があります。

### ④ ⚠️ 「バッジだけ静かに更新」はできない

**これが一番重要な制約です。**

> iOS は `showNotification()` を伴わない push を「サイレント」とみなし、
> 数回続くと**購読を勝手に解除します**。

つまり「通知は出さずにバッジの数字だけ増やす」という動きは iOS では作れません。
**プッシュを送るなら必ず通知バナーも出す**必要があります。

今回は「本が届いた」を知りたいので通知は出したいはずで、実害はありません。
ただし「静かに件数だけ管理する」という設計はできない、と理解しておく必要があります。

### ⑤ VAPID の subject は `mailto:` か HTTPS URL のみ

Apple のプッシュサーバーは、それ以外の形式だと **403 Forbidden** を返します。

### ⑥ ⚠️ 引っ越すと購読がリセットされる

プッシュの購読は**オリジン（ドメイン）に紐づきます**。

いま `https://monetmacbook-air.tail63c7e9.ts.net` で追加していますが、
将来 Cloud Run などに移すとドメインが変わるため、
**ホーム画面から削除して追加し直し、通知許可も取り直し**になります。

→ **順番の提案**: 先にドメインを決めてから通知を作るほうが、二度手間になりません。

---

## 3. 「誰が Gmail を見張るか」の選択肢

### 案A: Google Apps Script で定期チェック（おすすめ）

Google のサーバー上で動く無料のスクリプトです。時間トリガーで数分おきに
Gmail を検索し、図書館からのメールを見つけたら通知送信用のURLを叩きます。

```javascript
// イメージ（実装時に詰める）
function checkLibraryMail() {
  const threads = GmailApp.search('is:unread (from:gifu-lib.jp OR from:kani-lib.jp) 予約');
  if (threads.length === 0) return;
  UrlFetchApp.fetch('https://<通知送信URL>/notify', {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ count: threads.length }),
    headers: { 'Authorization': 'Bearer <合言葉>' },
  });
}
```

| 項目 | 内容 |
|---|---|
| 費用 | **無料** |
| 制限 | 1回の実行は6分まで／**無料アカウントはトリガー合計 90分/日** |
| 実際の消費 | 15分おき × 数秒 = 1日あたり数分。**余裕で収まります** |
| 遅延 | チェック間隔ぶん（15分おきなら最大15分） |
| 手間 | 小。ブラウザ上でスクリプトを書いて保存するだけ |

### 案B: Gmail API の watch + Pub/Sub（リアルタイム）

メールが届いた瞬間に Google 側から通知が飛んできます。

| 項目 | 内容 |
|---|---|
| 遅延 | ほぼゼロ |
| 手間 | 中〜大。GCPプロジェクト・Pub/Subトピック・OAuth の設定が必要 |
| 注意 | **7日以内に `watch` を呼び直さないと止まります**（1日1回の再呼び出しが推奨） |

予約本の到着は数分〜数十分遅れても困らないので、**案Aで十分**だと考えます。

### なぜ Apps Script が直接プッシュを送れないのか

「GAS だけで完結できないの？」という疑問が当然出ますが、**できません**。

Web Push は送信時に2つの暗号処理が要ります。

1. **VAPID の署名** — ES256（楕円曲線 P-256 の署名）
2. **本文の暗号化** — ECDH 鍵交換 + HKDF + AES-GCM

Apps Script が持っているのは HMAC 系だけで、**ECDSA も ECDH も無い**ため、
どちらも実装できません。したがって **Python 側（`pywebpush`）で送る**必要があります。

---

## 4. 送信側をどこに置くか（＝Mac問題）

ここが唯一の悩みどころです。

| 置き場所 | 通知が届くタイミング | 費用 |
|---|---|---|
| **今のMac（Tailscale）** | **Macが起動しているときだけ** | 無料 |
| Cloud Run | 常に届く | 無料枠内 |

### 補足: Mac 依存でも意外と実用になる

Apps Script 側で「まだ通知していないメール」を記録しておけば、
**Mac が寝ている間に届いたメールも、次に Mac を開いたときにまとめて通知**できます。

予約本は「今すぐ走らないと消える」ものではないので、
**まず Mac 依存で作ってみて、不便なら Cloud Run へ移す**のが現実的だと思います。

---

## 5. 実装の見積もり

| # | 作業 | 規模 |
|---|---|---|
| 1 | VAPID 鍵ペアを生成（`py_vapid`） | 5分 |
| 2 | 「🔔 通知をオンにする」ボタンを追加（クリックで許可要求 → 購読） | 小 |
| 3 | 購読情報を保存する API と保存先を作る | 小 |
| 4 | `sw.js` に `push` / `notificationclick` ハンドラを追加 | 小 |
| 5 | └ `push` の中で `showNotification()` **と** `setAppBadge(件数)` を呼ぶ | — |
| 6 | └ アプリを開いたら `clearAppBadge()` | — |
| 7 | 通知送信API（`pywebpush`、合言葉で保護） | 小 |
| 8 | Apps Script を書いて15分トリガーを設定 | 小 |
| 9 | 実機で確認（**シミュレータでは検証不可**） | — |

依存追加は `pywebpush` と `py-vapid` の2つだけです。合計で**1日かからない**見込み。

### バッジの扱い（設計案）

```
push受信         → 未読の予約通知メール件数を setAppBadge(n)
アプリを開いた   → clearAppBadge()
```

「未読メール件数」を数字の根拠にするのが一番素直です。
Gmail 側で既読にすれば自然に減ります。

---

## 6. 正直に言っておきたいこと

**すでに Gmail の通知は届いているので、これは「通知が増える」機能ではありません。**
やる価値があるとすれば、次の3点です。

1. **バッジで「何冊待っているか」が一目でわかる**（メール通知にはできない）
2. **岐阜市と可児市の通知が1か所にまとまる**
3. **通知をタップするとアプリが開く**ので、そのまま次の検索に移れる

逆に、通知が二重になる煩わしさは出ます。
その場合は Gmail 側でフィルタを作り、**図書館メールの通知だけ Gmail からは切る**と
きれいに住み分けできます。

---

## 7. おすすめの進め方

1. **先にドメインを決める**（Tailscale のままか、Cloud Run へ移すか）
   → 後から移すと通知の購読をやり直すことになるため
2. VAPID 鍵を作り、通知ボタンと `sw.js` のハンドラを実装
3. Mac 上に通知送信APIを立て、Apps Script から叩く
4. 実機で「メールが来る → 通知が出る → バッジが増える → 開くと消える」を確認
5. Mac 依存が不便なら Cloud Run へ移す

---

## 参考にした情報源

- [Badging for Home Screen Web Apps | WebKit](https://webkit.org/blog/14112/badging-for-home-screen-web-apps/)
- [Display a badge on the app icon | MDN](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/How_to/Display_badge_on_app_icon)
- [PWA iOS Limitations and Safari Support 2026 | MagicBell](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide)
- [PWA Push Notifications on iOS in 2026: What Really Works](https://webscraft.org/blog/pwa-pushspovischennya-na-ios-u-2026-scho-realno-pratsyuye?lang=en)
- [webpush-ios-example | GitHub](https://github.com/andreinwald/webpush-ios-example)
- [Configure push notifications in Gmail API | Google for Developers](https://developers.google.com/workspace/gmail/api/guides/push)
- [Google Apps Script の制限値ガイド](https://www.yoshidumi.co.jp/collaboration-lab/gas-quotas-and-solutions)
