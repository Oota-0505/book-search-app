"""実ブラウザ（Chrome）でPWAを検証する（PWA_GUIDE §10-2）。

Chrome を --remote-debugging-port で起動し、CDP 経由でページ内の
JavaScript を実行して Service Worker の登録状態などを確認する。

    .venv/bin/python tools/verify_pwa.py [URL]
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222

# PWA_GUIDE §10-2 の確認スクリプト
CHECK_SCRIPT = r"""
(async () => {
  // SW が activated になるまで待つ
  const reg = await navigator.serviceWorker.register("/sw.js").catch(e => ({ __error: e.message }));
  if (reg && reg.__error) return { registerError: reg.__error };

  await navigator.serviceWorker.ready;
  const r = await navigator.serviceWorker.getRegistration();
  const manifest = await (await fetch("/manifest.webmanifest")).json();
  const cacheNames = await caches.keys();

  // キャッシュの中身を調べる（HTMLやAPIが入っていないこと）
  let keys = [];
  if (cacheNames.length) {
    const cache = await caches.open(cacheNames[0]);
    keys = (await cache.keys()).map(req => req.method + " " + new URL(req.url).pathname);
  }

  return {
    secureContext: window.isSecureContext,
    swRegistered: !!r,
    swState: r && r.active ? r.active.state : null,
    scope: r ? r.scope : null,
    manifestName: manifest.name,
    icons: manifest.icons.length,
    caches: cacheNames,
    cachedKeys: keys,
    nonGet: keys.filter(k => !k.startsWith("GET ")),
    cachedHtml: keys.filter(k => k.endsWith("/") || k.endsWith(".html")),
    cachedApi: keys.filter(k => k.includes("/api/")),
  };
})()
"""


async def evaluate(ws_url: str, expression: str) -> dict:
    async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "awaitPromise": True, "returnByValue": True},
        }))
        while True:
            message = json.loads(await ws.recv())
            if message.get("id") == 1:
                result = message["result"]
                if "exceptionDetails" in result:
                    raise RuntimeError(result["exceptionDetails"])
                return result["result"]["value"]


def wait_for_target(url: str, timeout: float = 30.0) -> str:
    """デバッグ対象のページが現れるまで待ち、WebSocket URL を返す。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json") as res:
                for target in json.load(res):
                    if target.get("type") == "page" and target.get("url", "").startswith(url):
                        return target["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError("Chrome のデバッグ対象が見つかりませんでした")


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"
    profile = tempfile.mkdtemp(prefix="pwa-verify-")

    chrome = subprocess.Popen(
        [
            CHROME, "--headless=new", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-gpu",
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={profile}",
            url,
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        ws_url = wait_for_target(url.rstrip("/"))
        report = asyncio.run(evaluate(ws_url, CHECK_SCRIPT))
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        shutil.rmtree(profile, ignore_errors=True)

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report.get("registerError"):
        print(f"\n❌ Service Worker の登録に失敗: {report['registerError']}")
        return 1

    checks = [
        ("secure context",            report["secureContext"] is True),
        ("SW が登録されている",        report["swRegistered"] is True),
        ("SW が activated",           report["swState"] == "activated"),
        ("スコープがルート",           str(report["scope"]).endswith("/")),
        ("manifest が読める",          bool(report["manifestName"])),
        ("アイコンが4種",              report["icons"] >= 4),
        ("キャッシュが作られている",    len(report["caches"]) > 0),
        ("GET以外を入れていない",       report["nonGet"] == []),
        ("HTMLはoffline.htmlのみ",     all("offline" in k for k in report["cachedHtml"])),
        ("APIを入れていない",           report["cachedApi"] == []),
    ]

    print()
    failed = 0
    for label, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label}")
        failed += not ok

    print(f"\n{'✅ すべて合格' if not failed else f'❌ {failed} 件が不合格'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
