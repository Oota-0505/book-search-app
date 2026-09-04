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
})();
