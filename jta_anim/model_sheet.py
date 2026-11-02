"""Render the cast model sheet: python -m jta_anim.model_sheet out.png"""
import sys

from . import cast
from .core import label, render, rgb, text
from .theme import C, W, H


def draw(ctx, t, f):
    rgb(ctx, C["papyrus"])
    ctx.paint()
    label(ctx, "JTA cast · model sheet", W / 2, 90, 34)
    fy = 900
    cast.jesus(ctx, 260, fy, 640)
    cast.jesus(ctx, 590, fy, 640, step=1, sway=1)
    import math
    ctx.save()
    ctx.arc(960, 560, 190, 0, 2 * math.pi)
    rgb(ctx, C["papyrus_dark"]); ctx.fill_preserve(); ctx.clip()
    cast.jesus_hands(ctx, 960, 540, 260, open_=0.5)
    ctx.restore()
    ctx.arc(960, 560, 190, 0, 2 * math.pi)
    rgb(ctx, C["ink"]); ctx.set_line_width(5); ctx.stroke()
    cast.seeker(ctx, 1340, fy, 600, view="front")
    cast.seeker(ctx, 1670, fy, 600, view="back")
    for x, s in ((260, "Jesus, behind"), (590, "Jesus, walking"), (960, "His hands"),
                 (1340, "Seeker, front"), (1670, "Seeker, back")):
        text(ctx, s.upper(), x, fy + 66, 22, C["ink"], spacing=3)
    sw = [("tunic", "jesus_tunic"), ("mantle", "jesus_mantle"), ("hair", "jesus_hair"), ("robe", "seeker_robe"),
          ("skin", "skin"), ("gold", "gold"), ("terracotta", "terracotta"), ("olive", "olive"), ("indigo", "indigo")]
    x0 = W / 2 - len(sw) * 120 / 2
    for i, (n, k) in enumerate(sw):
        x = x0 + i * 120 + 60
        ctx.rectangle(x - 22, 1000, 44, 30)
        rgb(ctx, C[k]); ctx.fill_preserve(); rgb(ctx, C["ink"]); ctx.set_line_width(2); ctx.stroke()
        text(ctx, n, x, 1062, 20, C["ink"])


if __name__ == "__main__":
    render(draw, 0, sys.argv[1] if len(sys.argv) > 1 else "model_sheet.png", still_at=0)
