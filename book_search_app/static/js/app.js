/*
 * Book Finder — フロントエンド
 *
 * 最初のHTMLは検索結果を含まずに即座に返る。
 * 検索は /api/search を fetch して、返ってきたJSONからカードを組み立てる。
 */

(() => {
    "use strict";

    const form = document.getElementById("search-form");
    const input = document.getElementById("keyword");
    const searchBtn = document.getElementById("search-btn");
    const amazonBtn = document.getElementById("amazon-btn");
    const historyBox = document.getElementById("history");
    const historyChips = document.getElementById("history-chips");
    const resultsArea = document.getElementById("results-area");
    const loadingTpl = document.getElementById("tpl-loading");

    /** 進行中の検索。新しい検索が始まったら前のものは捨てる。 */
    let inflight = null;

    // ── 小さなDOMヘルパー ───────────────────────────────────────
    const el = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        // textContent で入れるので、キーワードに < や " が含まれても壊れない
        if (text !== undefined) node.textContent = text;
        return node;
    };

    const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };

    // ── 結果カード ──────────────────────────────────────────────
    function buildCard(result) {
        const card = el("article", `card tone-${result.status.tone}`);
        if (result.image) card.style.backgroundImage = `url("${result.image}")`;

        card.appendChild(el("div", "card-overlay"));

        const content = el("div", "card-content");
        const top = el("div", "card-top");

        const site = el("div", "site");
        site.appendChild(el("span", "site-icon", result.icon));
        site.appendChild(el("span", "site-title", result.name));
        top.appendChild(site);

        top.appendChild(
            el("div", `pill tone-${result.status.tone}`,
               `${result.status.icon} ${result.status.text}`),
        );
        content.appendChild(top);

        const link = el("a", "card-link", "結果を開く ↗");
        link.href = result.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        content.appendChild(link);

        card.appendChild(content);
        return card;
    }

    function renderResults(data) {
        clear(resultsArea);

        resultsArea.appendChild(
            el("h2", "results-title", `「${data.keyword}」の検索結果`),
        );
        if (data.cached) {
            resultsArea.appendChild(
                el("p", "results-note",
                   "※ 直近10分以内の結果を再利用しています（各サイトへの再アクセスなし）"),
            );
        }

        const grid = el("div", "results-grid");
        data.results.forEach((r) => grid.appendChild(buildCard(r)));
        resultsArea.appendChild(grid);
    }

    function renderMessage(message) {
        clear(resultsArea);
        resultsArea.appendChild(el("p", "alert", message));
    }

    function renderLoading() {
        clear(resultsArea);
        resultsArea.appendChild(loadingTpl.content.cloneNode(true));
    }

    // ── 検索履歴 ────────────────────────────────────────────────
    function renderHistory(history) {
        clear(historyChips);
        history.forEach((keyword) => {
            const chip = el("button", "chip", keyword);
            chip.type = "button";
            historyChips.appendChild(chip);
        });
        historyBox.hidden = history.length === 0;
    }

    historyChips.addEventListener("click", (event) => {
        const chip = event.target.closest(".chip");
        if (!chip) return;
        input.value = chip.textContent;
        runSearch();
    });

    // ── 検索の実行 ──────────────────────────────────────────────
    async function runSearch() {
        const keyword = input.value.trim();
        if (!keyword) {
            renderMessage("⚠️ キーワードを入力してください");
            input.focus();
            return;
        }

        if (inflight) inflight.abort();
        const controller = new AbortController();
        inflight = controller;

        searchBtn.disabled = true;
        renderLoading();
        resultsArea.scrollIntoView({ behavior: "smooth", block: "nearest" });

        try {
            const res = await fetch(
                `/api/search?q=${encodeURIComponent(keyword)}`,
                { signal: controller.signal, headers: { Accept: "application/json" } },
            );
            const data = await res.json();

            if (!res.ok) {
                renderMessage(`⚠️ ${data.error || "検索に失敗しました"}`);
                return;
            }

            renderResults(data);
            renderHistory(data.history || []);
        } catch (error) {
            if (error.name === "AbortError") return;   // 新しい検索に置き換わっただけ
            renderMessage(
                navigator.onLine
                    ? "⚠️ 検索に失敗しました。しばらくしてからもう一度お試しください。"
                    : "⚠️ オフラインのため検索できません。通信状況をご確認ください。",
            );
        } finally {
            if (inflight === controller) {
                inflight = null;
                searchBtn.disabled = false;
            }
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        runSearch();
    });

    // ── Amazon ボタン ───────────────────────────────────────────
    // Streamlit 時代は親ドキュメントの input を総当たりで探していたが、
    // 素のHTMLになったので入力欄を直接読むだけで済む。
    amazonBtn.addEventListener("click", () => {
        const keyword = input.value.trim();
        if (!keyword) {
            input.focus();
            return;
        }
        const url = "https://www.amazon.co.jp/s?"
            + `k=${encodeURIComponent(keyword)}&i=stripbooks`;
        window.open(url, "_blank", "noopener");
    });

    // ── Service Worker ──────────────────────────────────────────
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js").catch((error) => {
                // 登録できなくてもアプリは動くので、握りつぶさず記録だけ残す
                console.info("Service worker was not registered:", error.message);
            });
        });
    }

    // ── プッシュ通知 ────────────────────────────────────────────
    const pushBtn = document.getElementById("push-btn");

    /**
     * base64url の公開鍵を Uint8Array に変換する。
     * ⚠️ Safari は文字列のままの applicationServerKey を受け付けないので必須。
     */
    function urlBase64ToUint8Array(base64String) {
        const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
        const raw = atob(base64);
        return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
    }

    function markPushEnabled() {
        pushBtn.textContent = "🔔 通知はオンです";
        pushBtn.disabled = true;
    }

    async function enablePush() {
        pushBtn.disabled = true;
        try {
            // ⚠️ iOS では「クリックハンドラの中」でしか許可を求められない。
            //    setTimeout やページ読み込み時に呼ぶと黙って無視される。
            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
                renderMessage(
                    "⚠️ 通知が許可されませんでした。iPhoneの「設定 → 通知」から変更できます。",
                );
                pushBtn.disabled = false;
                return;
            }

            const registration = await navigator.serviceWorker.ready;
            const { key } = await (await fetch("/api/push/key")).json();

            // すでに購読済みならそれを使い回す（重複登録を避ける）
            const subscription =
                (await registration.pushManager.getSubscription())
                || (await registration.pushManager.subscribe({
                    userVisibleOnly: true,          // iOS では true 必須
                    applicationServerKey: urlBase64ToUint8Array(key),
                }));

            await syncSubscription(subscription);
            markPushEnabled();
        } catch (error) {
            console.error("プッシュ購読に失敗:", error);
            renderMessage(`⚠️ 通知の登録に失敗しました: ${error.message}`);
            pushBtn.disabled = false;
        }
    }

    /** 購読情報をサーバーへ送る（同じ endpoint は上書きされるので何度呼んでもよい）。 */
    async function syncSubscription(subscription) {
        const res = await fetch("/api/push/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(subscription),
        });
        if (!res.ok) throw new Error(`購読の保存に失敗しました (${res.status})`);
    }

    /**
     * ボタンの表示を実態に合わせる。
     *
     * ⚠️ 「通知が許可されている」と「購読が登録されている」は別物。
     *    Notification.permission だけで判断すると、許可済みなのに未購読という
     *    状態（PWAを入れ直した直後など）でボタンが「オン」と嘘をつき、
     *    購読し直す手段が無くなる。実際の購読の有無で判断する。
     */
    async function refreshPushButton() {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        if (!subscription) return;

        // 端末に購読があってもサーバーが失っていることがあるので必ず再送する。
        // ここを握りつぶすと「オンと表示されているのに通知が来ない」状態になり、
        // 原因が分からなくなる。失敗したら購読し直せるようにボタンを戻す。
        try {
            await syncSubscription(subscription);
            markPushEnabled();
        } catch (error) {
            console.error("購読の再同期に失敗:", error);
            renderMessage(
                `⚠️ 通知の登録がサーバーに届いていません（${error.message}）。`
                + "もう一度「🔔 通知をオンにする」を押してください。",
            );
        }
    }

    if ("Notification" in window && "PushManager" in window && "serviceWorker" in navigator) {
        pushBtn.hidden = false;
        pushBtn.addEventListener("click", enablePush);
        refreshPushButton().catch((error) => {
            console.info("購読状態の確認に失敗:", error.message);
        });
    }
    // ↑ 対応していない環境（Safariのタブなど）では hidden のまま。
    //   iOS はホーム画面に追加したPWAでしか PushManager を持たない。

    // ── 受取待ちの本 ────────────────────────────────────────────
    const pendingBox = document.getElementById("pending");
    const pendingTitle = document.getElementById("pending-title");
    const pendingList = document.getElementById("pending-list");

    /** 2026-09-13 → 9/13 */
    function formatDue(iso) {
        const [, month, day] = iso.split("-");
        return `${Number(month)}/${Number(day)}`;
    }

    function buildPendingItem(book) {
        const item = el("li", "pending-item");
        // 期限を過ぎると予約が取り消されるので、近いものほど目立たせる
        if (book.days_left < 0) item.classList.add("over");
        else if (book.days_left <= 3) item.classList.add("soon");

        const main = el("div", "pending-main");
        main.appendChild(el("div", "pending-book", book.title));

        const meta = el("div", "pending-meta");
        meta.append(`${book.where} ・ `);

        const due = el("span", "pending-due");
        if (book.days_left < 0) due.textContent = `${formatDue(book.due)}まで（期限切れ）`;
        else if (book.days_left === 0) due.textContent = `${formatDue(book.due)}まで（今日まで）`;
        else due.textContent = `${formatDue(book.due)}まで（あと${book.days_left}日）`;
        meta.appendChild(due);

        // 岐阜市は「7開館日」からの推定なので、根拠を添えて誤解を防ぐ
        if (book.due_is_estimate) {
            meta.appendChild(el("span", "pending-estimate", " ※最短。休館日があればもう少し余裕あり"));
        }
        main.appendChild(meta);
        item.appendChild(main);

        const done = el("button", "pending-done", "受け取った");
        done.type = "button";
        done.dataset.id = book.id;
        item.appendChild(done);

        return item;
    }

    function renderPending(books) {
        pendingList.replaceChildren();
        if (!books.length) {
            pendingBox.hidden = true;
            if (navigator.clearAppBadge) navigator.clearAppBadge().catch(() => {});
            return;
        }
        pendingTitle.textContent = `📚 受取待ちの本（${books.length}冊）`;
        books.forEach((book) => pendingList.appendChild(buildPendingItem(book)));
        pendingBox.hidden = false;
        if (navigator.setAppBadge) navigator.setAppBadge(books.length).catch(() => {});
    }

    async function loadPending() {
        try {
            const { books } = await (await fetch("/api/pending")).json();
            renderPending(books || []);
        } catch (error) {
            console.info("受取待ちリストの取得に失敗:", error.message);
        }
    }

    pendingList.addEventListener("click", async (event) => {
        const button = event.target.closest(".pending-done");
        if (!button) return;
        button.disabled = true;
        try {
            const res = await fetch(`/api/pending/${button.dataset.id}`, { method: "DELETE" });
            const { books } = await res.json();
            renderPending(books || []);
        } catch (error) {
            button.disabled = false;
            renderMessage(`⚠️ 受取済みにできませんでした: ${error.message}`);
        }
    });

    loadPending();

    // ── 通知の診断 ──────────────────────────────────────────────
    // 実機でしか分からない状態（standalone か・許可・SWの版・購読の有無）を
    // 画面に出す。通知が来ないときの原因切り分け用。
    const diag = document.getElementById("diag");
    const diagBody = document.getElementById("diag-body");
    const diagResult = document.getElementById("diag-result");

    function row(label, value, ok) {
        const dt = el("dt", "", label);
        const dd = el("dd", ok === undefined ? "" : (ok ? "ok" : "ng"), value);
        diagBody.append(dt, dd);
    }

    async function renderDiagnostics() {
        diagBody.replaceChildren();

        const standalone = window.matchMedia("(display-mode: standalone)").matches
            || window.navigator.standalone === true;
        row("ホーム画面から起動", standalone ? "はい" : "いいえ（Safariのタブ）", standalone);

        const hasPush = "PushManager" in window;
        row("Push API", hasPush ? "使える" : "使えない", hasPush);

        const permission = ("Notification" in window) ? Notification.permission : "なし";
        row("通知の許可", permission, permission === "granted");

        let registration = null;
        try {
            registration = await navigator.serviceWorker.getRegistration();
        } catch (error) { /* 取得できないこともある */ }
        row("Service Worker", registration?.active ? registration.active.state : "未登録",
            Boolean(registration?.active));

        let subscription = null;
        if (registration) {
            try {
                subscription = await registration.pushManager.getSubscription();
            } catch (error) { /* 未対応環境 */ }
        }
        row("この端末の購読", subscription ? subscription.endpoint.slice(0, 42) + "…" : "なし",
            Boolean(subscription));

        try {
            const status = await (await fetch("/api/push/status")).json();
            row("サーバーの登録数", `${status.count} 件`, status.count > 0);
        } catch (error) {
            row("サーバーの登録数", `取得できない（${error.message}）`, false);
        }
    }

    document.getElementById("diag-test").addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        diagResult.textContent = "送信中…";
        try {
            const res = await fetch("/api/push/test", { method: "POST" });
            const data = await res.json();
            diagResult.textContent = data.sent > 0
                ? `送信しました（${data.sent}件）。通知が出ない場合はiPhoneの「設定 → 通知」を確認してください。`
                : "送信先がありません。「🔔 通知をオンにする」を押してください。";
        } catch (error) {
            diagResult.textContent = `送信に失敗: ${error.message}`;
        } finally {
            button.disabled = false;
            renderDiagnostics();
        }
    });

    if ("serviceWorker" in navigator) {
        diag.hidden = false;
        renderDiagnostics();
        diag.addEventListener("toggle", () => { if (diag.open) renderDiagnostics(); });
    }

    // ── プッシュから開かれたときの案内 ──────────────────────────
    // ⚠️ iOS は通知タップで別オリジンへ飛べないため、
    //    アプリ側でリンクを出して1タップで行けるようにする。
    if (new URLSearchParams(location.search).get("from") === "push") {
        // バッジは loadPending() が受取待ちの冊数に合わせて調整するので、
        // ここでは消さない（まだ取りに行っていない本が残っているため）
        const box = el("div", "alert push-notice");
        box.append("📚 予約本が届いています ");

        const link = el("a", "", "メディコスのマイページを開く ↗");
        link.href = "https://www1.gifu-lib.jp/winj/opac/login.do"
            + "?lang=ja&dispatch=/opac/mylibrary.do&every=1";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        box.appendChild(link);

        resultsArea.prepend(box);
    }
})();
