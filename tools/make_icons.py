"""PWA アイコンを生成する（アプリのヒーローSVGと同じ「本＋虫眼鏡」の意匠）。

    .venv/bin/python tools/make_icons.py

4倍の大きさで描いてから縮小することでアンチエイリアスをかけている。
maskable と apple-touch-icon は不透明にする（iOS は透過を黒く描くため）。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ICONS_DIR = Path(__file__).resolve().parent.parent / "book_search_app" / "static" / "icons"

SS = 4  # スーパーサンプリング倍率

INK = (12, 8, 32, 255)          # 背景（アプリの --ink と同じ）
COVER = (37, 99, 235, 255)      # 本の表紙
COVER_EDGE = (30, 64, 175, 255)
PAGE = (255, 255, 255, 255)
PAGE_EDGE = (203, 213, 225, 255)
BOOKMARK = (239, 68, 68, 255)
GLASS_RIM = (255, 255, 255, 255)
GLASS_FILL = (224, 242, 254, 235)
GLASS_INK = (31, 41, 55, 255)


def _draw_logo(size: int, inset: float, background: tuple | None) -> Image.Image:
    """1枚のアイコンを描く（開いた本＋その上にかざした虫眼鏡）。

    Args:
        size: 出力する一辺のピクセル数
        inset: 図柄が占める割合（maskable は 0.6 前後にして余白を作る）
        background: 背景色。None なら透過
    """
    big = size * SS
    image = Image.new("RGBA", (big, big), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if background is not None:
        # 角丸の下地（Android が円や角丸に切り抜いても破綻しないよう全面に敷く）
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.18), fill=background)

    # ── 図柄の座標系（0..1 を inset 倍して中央へ寄せる）──
    span = big * inset
    ox = (big - span) / 2
    oy = (big - span) / 2

    def p(x: float, y: float) -> tuple[float, float]:
        return (ox + x * span, oy + y * span)

    line_w = max(1, int(span * 0.020))

    # ── 開いた本（下 6 割）──
    draw.polygon(
        [p(0.02, 0.44), p(0.50, 0.52), p(0.98, 0.44), p(0.98, 0.93), p(0.50, 1.00), p(0.02, 0.93)],
        fill=COVER, outline=COVER_EDGE, width=line_w,
    )
    draw.polygon(
        [p(0.10, 0.47), p(0.50, 0.55), p(0.50, 0.94), p(0.10, 0.87)],
        fill=PAGE, outline=PAGE_EDGE, width=line_w,
    )
    draw.polygon(
        [p(0.90, 0.47), p(0.50, 0.55), p(0.50, 0.94), p(0.90, 0.87)],
        fill=PAGE, outline=PAGE_EDGE, width=line_w,
    )
    draw.line([p(0.50, 0.55), p(0.50, 0.94)], fill=PAGE_EDGE, width=line_w)

    # 本文を示す罫線（左右のページに数本ずつ）
    for i, y in enumerate((0.65, 0.72, 0.79)):
        drop = 0.012 * (i + 1)
        draw.line([p(0.17, y - 0.05 + drop), p(0.43, y + drop)], fill=PAGE_EDGE, width=line_w)
        draw.line([p(0.83, y - 0.05 + drop), p(0.57, y + drop)], fill=PAGE_EDGE, width=line_w)

    # しおり
    draw.polygon(
        [p(0.50, 0.55), p(0.545, 0.68), p(0.50, 0.73), p(0.455, 0.68)],
        fill=BOOKMARK,
    )

    # ── 虫眼鏡（本の上にかざす。持ち手は右下へ）──
    cx, cy, r = 0.44, 0.28, 0.235
    grip_from = p(cx + r * 0.70, cy + r * 0.70)
    grip_to = p(cx + r * 1.75, cy + r * 1.75)

    # 白フチ（背景から浮かせる）
    draw.line([grip_from, grip_to], fill=GLASS_RIM, width=int(span * 0.090))
    draw.ellipse([p(cx - r, cy - r), p(cx + r, cy + r)],
                 outline=GLASS_RIM, width=int(span * 0.062))
    # 本体
    draw.line([grip_from, grip_to], fill=GLASS_INK, width=int(span * 0.052))
    draw.ellipse([p(cx - r, cy - r), p(cx + r, cy + r)],
                 fill=GLASS_FILL, outline=GLASS_INK, width=int(span * 0.034))
    # レンズのハイライト
    draw.arc([p(cx - r * 0.62, cy - r * 0.62), p(cx + r * 0.62, cy + r * 0.62)],
             start=185, end=250, fill=(255, 255, 255, 255), width=int(span * 0.026))

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        # (ファイル名, サイズ, 図柄の占有率, 背景)
        ("icon-192.png", 192, 0.80, INK),
        ("icon-512.png", 512, 0.80, INK),
        ("maskable-192.png", 192, 0.58, INK),   # Android が切り抜くので中央60%程度へ
        ("maskable-512.png", 512, 0.58, INK),
        ("apple-touch-icon.png", 180, 0.78, INK),
    ]

    for name, size, inset, background in targets:
        image = _draw_logo(size, inset, background)
        if name.startswith(("maskable", "apple")):
            # iOS/Android 向けは透過を残さない
            image = image.convert("RGB")
        image.save(ICONS_DIR / name, "PNG", optimize=True)
        print(f"{name:24s} {size}x{size}  {(ICONS_DIR / name).stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
