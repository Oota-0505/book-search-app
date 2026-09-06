/*
 * Service Worker — Book Finder
 *
 * 役割は3つ。
 *   1. インストール可能にする
 *   2. 圏外で真っ白にせず、案内を出す
 *   3. 静的アセット（CSS・JS・画像・アイコン）をキャッシュして2回目以降の起動を速くする
 *
 * HTML と API のレスポンスはキャッシュしない。
 * 在庫状況は時間で変わるので、古い結果を見せる事故のほうが害が大きい。
 *
 * ★ このファイルを編集したら VERSION を必ず上げること。
 *   上げ忘れると、端末に古いSWが残り続ける。
 */

const VERSION = "v2";
const STATIC_CACHE = `book-finder-static-${VERSION}`;
const OFFLINE_URL = "/offline.html";

const PRECACHE = [
    OFFLINE_URL,
    "/manifest.webmanifest",
    "/static/icons/icon-192.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => cache.addAll(PRECACHE))
            .then(() => self.skipWaiting()),
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key)),
            ))
            .then(() => self.clients.claim()),
    );
});

self.addEventListener("fetch", (event) => {
    const { request } = event;

    // GET以外は絶対に触らない
    if (request.method !== "GET") return;

    const url = new URL(request.url);

    // 別ドメイン（各図書館・書店サイトなど）は素通し
    if (url.origin !== self.location.origin) return;

    // 画面遷移：ネットワーク優先、落ちたらオフライン画面
    if (request.mode === "navigate") {
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
        return;
    }

    // 在庫は時間で変わるので API は常にネットワークへ
    if (url.pathname.startsWith("/api/")) return;

    const cacheable =
        url.pathname.startsWith("/static/") ||
        url.pathname === "/manifest.webmanifest" ||
        url.pathname === "/favicon.ico";

    if (!cacheable) return;

    event.respondWith(
        caches.match(request).then((hit) => {
            if (hit) return hit;

            return fetch(request).then((response) => {
                if (!response.ok || response.status !== 200) return response;

                const copy = response.clone();
                caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy));

                return response;
            });
        }),
    );
});


/* ── プッシュ通知 ───────────────────────────────────────────── */

self.addEventListener("push", (event) => {
    const data = event.data ? event.data.json() : {};

    event.waitUntil((async () => {
        // ⚠️ iOS では showNotification を必ず呼ぶこと。
        //    省略すると「サイレントpush」とみなされ、購読を解除される。
        await self.registration.showNotification(data.title || "Book Finder", {
            body: data.body || "",
            icon: "/static/icons/icon-192.png",
            badge: "/static/icons/icon-192.png",
            data: { url: data.url || "/" },
        });

        // アイコンに数字を出す（iOS 16.4+ / ホーム画面追加済みのときだけ効く）
        if (typeof data.count === "number" && self.navigator.setAppBadge) {
            await self.navigator.setAppBadge(data.count);
        }
    })());
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || "/";

    event.waitUntil((async () => {
        // ⚠️ iOS では clients.openWindow() で別オリジンへ飛べない。
        //    必ず自分のオリジン内へ遷移させ、案内リンクは画面側に出すこと。
        const windows = await self.clients.matchAll({
            type: "window",
            includeUncontrolled: true,
        });

        for (const client of windows) {
            if (new URL(client.url).origin === self.location.origin) {
                await client.navigate(url);
                return client.focus();
            }
        }
        return self.clients.openWindow(url);
    })());
});