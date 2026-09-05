"""用意した1枚の画像から、PWA用アイコン5種を書き出す。

    .venv/bin/python tools/make_icons_from_image.py path/to/logo.png

元画像は「正方形・512px以上・余白すこし」が理想。
maskable と apple-touch-icon は不透明にする（iOS は透過を黒く描くため）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ICONS_DIR = Path(__file__).resolve().parent.parent / "book_search_app" / "static" / "icons"
BACKGROUND = (12, 8, 32)  # アプリの --ink と同じ #0C0820


def _fit(source: Image.Image, size: int, scale: float, opaque: bool) -> Image.Image:
    """size×size の canvas の中央に、scale の割合で元画像を収める。"""
    canvas = Image.new("RGBA", (size, size), (*BACKGROUND, 255) if opaque else (0, 0, 0, 0))

    inner = max(1, int(size * scale))
    art = source.copy()
    art.thumbnail((inner, inner), Image.LANCZOS)

    canvas.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
    return canvas.convert("RGB") if opaque else canvas


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    source_path = Path(sys.argv[1])
    if not source_path.is_file():
        print(f"見つかりません: {source_path}")
        return 1

    with Image.open(source_path) as image:
        source = image.convert("RGBA")

    if source.width != source.height:
        print(f"⚠️ 正方形ではありません（{source.width}x{source.height}）。中央に収めます。")

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        # (ファイル名, サイズ, 図柄の占有率, 不透明にするか)
        ("icon-192.png", 192, 1.00, True),
        ("icon-512.png", 512, 1.00, True),
        # Android は円や角丸に切り抜くので、中央60%程度に収めて余白を作る
        ("maskable-192.png", 192, 0.60, True),
        ("maskable-512.png", 512, 0.60, True),
        ("apple-touch-icon.png", 180, 0.98, True),
    ]

    for name, size, scale, opaque in targets:
        _fit(source, size, scale, opaque).save(ICONS_DIR / name, "PNG", optimize=True)
        print(f"{name:24s} {size}x{size}  {(ICONS_DIR / name).stat().st_size / 1024:6.1f} KB")

    print("\n次: .venv/bin/python -m pytest tests/test_pwa.py -q で四隅の不透明性を確認")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
