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
FALLBACK_BACKGROUND = (12, 8, 32)  # アプリの --ink と同じ #0C0820


def _background_of(image: Image.Image) -> tuple[int, int, int]:
    """元画像の下地の色を、縁のピクセルの中央値から推定する。

    自前の色で塗ると、元画像の背景とわずかに違ったときに
    maskable 版で四角い継ぎ目が見えてしまう。生成画像の背景は
    圧縮ノイズで数値がばらつくため、単純な四隅の一致判定ではなく
    中央値を使う（外れ値に強い）。

    縁に絵がはみ出しているなど、色がまとまらない場合は既定色にする。
    """
    rgb = image.convert("RGB")
    w, h = rgb.size
    step = max(1, min(w, h) // 32)

    samples: list[tuple[int, int, int]] = []
    for x in range(0, w, step):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, h - 1)))
    for y in range(0, h, step):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((w - 1, y)))

    channels = [sorted(s[i] for s in samples) for i in range(3)]
    median = tuple(c[len(c) // 2] for c in channels)

    # 縁の色が散らばりすぎている＝一様な下地ではない、と判断する
    spread = max(c[-1] - c[0] for c in channels)
    if spread > 60:
        print(f"⚠️ 縁の色が一様ではありません（ばらつき {spread}）。既定色を使います。")
        return FALLBACK_BACKGROUND

    return median  # type: ignore[return-value]


def _crop_to_artwork(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """下地だけの余白を切り落として、絵の部分だけにする。

    生成された画像は絵のまわりに広い余白を持つことが多く、そのまま使うと
    ホーム画面で絵が小さく見える。余白を削ってから拡大するほうが視認性が高い。
    """
    rgb = image.convert("RGB")
    # 下地との差が小さいピクセルを「余白」とみなす（圧縮ノイズに耐えるため閾値つき）
    diff = Image.new("L", rgb.size)
    px_src, px_dst = rgb.load(), diff.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = px_src[x, y]
            d = abs(r - background[0]) + abs(g - background[1]) + abs(b - background[2])
            px_dst[x, y] = 255 if d > 30 else 0

    box = diff.getbbox()
    if box is None:
        return image

    # 正方形に整えてから切り出す（縦横比を崩さないため）
    left, top, right, bottom = box
    cx, cy = (left + right) / 2, (top + bottom) / 2
    half = max(right - left, bottom - top) / 2
    side = half * 2
    return image.crop((
        int(cx - half), int(cy - half), int(cx - half + side), int(cy - half + side),
    ))


def _fit(
    source: Image.Image, size: int, scale: float, opaque: bool,
    background: tuple[int, int, int],
) -> Image.Image:
    """size×size の canvas の中央に、scale の割合で元画像を収める。"""
    canvas = Image.new("RGBA", (size, size), (*background, 255) if opaque else (0, 0, 0, 0))

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

    background = _background_of(source)
    print(f"下地の色: #{background[0]:02X}{background[1]:02X}{background[2]:02X}")

    before = source.size
    source = _crop_to_artwork(source, background)
    print(f"余白を切り落とし: {before[0]}x{before[1]} → {source.size[0]}x{source.size[1]}\n")

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        # (ファイル名, サイズ, 図柄の占有率, 不透明にするか)
        # 余白を切り落としてあるので、ここでの割合がそのまま見た目の大きさになる
        ("icon-192.png", 192, 0.92, True),
        ("icon-512.png", 512, 0.92, True),
        # Android は円や角丸に切り抜くので、中央70%に収めて余白を作る
        ("maskable-192.png", 192, 0.70, True),
        ("maskable-512.png", 512, 0.70, True),
        # iOS は角を丸めるだけなので大きめでよい
        ("apple-touch-icon.png", 180, 0.88, True),
    ]

    for name, size, scale, opaque in targets:
        _fit(source, size, scale, opaque, background).save(
            ICONS_DIR / name, "PNG", optimize=True
        )
        print(f"{name:24s} {size}x{size}  {(ICONS_DIR / name).stat().st_size / 1024:6.1f} KB")

    print("\n次: .venv/bin/python -m pytest tests/test_pwa.py -q で四隅の不透明性を確認")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
