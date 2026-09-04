"""PWA の構成が壊れていないことを固定するテスト（PWA_GUIDE §10-3）。

    .venv/bin/python -m pytest tests/ -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

STATIC = Path(__file__).resolve().parent.parent / "book_search_app" / "static"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))


# ── manifest ────────────────────────────────────────────────────

def test_manifest_has_required_fields(manifest: dict) -> None:
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["name"] and manifest["short_name"]

    sizes = [icon["sizes"] for icon in manifest["icons"]]
    assert "192x192" in sizes and "512x512" in sizes
    assert "maskable" in [icon.get("purpose") for icon in manifest["icons"]]


def test_every_icon_exists_with_declared_size(manifest: dict) -> None:
    for icon in manifest["icons"]:
        path = STATIC / icon["src"].removeprefix("/static/")
        assert path.is_file(), f"{icon['src']} が無い"

        with Image.open(path) as image:
            assert f"{image.width}x{image.height}" == icon["sizes"]


# ── アイコン ────────────────────────────────────────────────────

def test_apple_touch_icon_is_opaque() -> None:
    """iOS は透過を黒く描くので、四隅が塗られていること。"""
    with Image.open(STATIC / "icons/apple-touch-icon.png") as image:
        assert image.size == (180, 180)
        rgba = image.convert("RGBA")
        for xy in [(0, 0), (179, 0), (0, 179), (179, 179)]:
            assert rgba.getpixel(xy)[3] == 255, f"{xy} が透過している"


@pytest.mark.parametrize("name,size", [("maskable-192.png", 192), ("maskable-512.png", 512)])
def test_maskable_icons_are_opaque(name: str, size: int) -> None:
    """Android が円や角丸に切り抜くので、四隅まで不透明であること。"""
    with Image.open(STATIC / "icons" / name) as image:
        assert image.size == (size, size)
        rgba = image.convert("RGBA")
        for xy in [(0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)]:
            assert rgba.getpixel(xy)[3] == 255, f"{name} の {xy} が透過している"


# ── Service Worker のキャッシュ方針 ─────────────────────────────

@pytest.fixture(scope="module")
def sw_source() -> str:
    return (STATIC / "sw.js").read_text(encoding="utf-8")


def test_service_worker_policy(sw_source: str) -> None:
    """キャッシュ方針が緩められていないことを固定する。"""
    assert 'request.method !== "GET"' in sw_source, "GET以外を素通ししていない"
    assert 'request.mode === "navigate"' in sw_source, "画面がネットワーク優先になっていない"
    assert "url.origin !== self.location.origin" in sw_source, "別ドメインを素通ししていない"


def test_service_worker_never_caches_the_api(sw_source: str) -> None:
    """在庫は時間で変わるので、APIレスポンスをキャッシュしてはいけない。"""
    assert 'url.pathname.startsWith("/api/")' in sw_source


def test_offline_page_loads_no_external_resources() -> None:
    """オフライン画面は読み込めない状況で出るので、外部参照を持たないこと。"""
    html = (STATIC / "offline.html").read_text(encoding="utf-8")
    for forbidden in ("<link rel=\"stylesheet\"", "fonts.googleapis", "https://", "<img"):
        assert forbidden not in html, f"offline.html が {forbidden} を含んでいる"
