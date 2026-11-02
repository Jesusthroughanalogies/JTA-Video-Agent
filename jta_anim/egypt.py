"""The ancient Egyptian environment behind the animations (earth tones, thick outlines).

Layers: papyrus sky, sun disc, pyramids and dunes, date palms, painted lotus columns at the
edges, a painted frieze along the top and a zig-zag band along the bottom. The centre stays
calm so the teaching content reads clearly.
"""
from __future__ import annotations

import math

import cairo

from .core import diamond, mix, outline_fill, rgb
from .theme import C, H, OUTLINE, W

HORIZON = 735


def _sky(ctx: cairo.Context, night: bool) -> None:
    g = cairo.LinearGradient(0, 0, 0, HORIZON)
    top, low = (C["night_bg"], mix(C["night_bg"], C["indigo"], 0.35)) if night else (C["sky_top"], C["sky_low"])
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(1, *low)
    ctx.set_source(g)
    ctx.paint()


def _sun(ctx: cairo.Context, night: bool) -> None:
    x, y, r = 1390, 330, 92
    halo = cairo.RadialGradient(x, y, r * 0.8, x, y, r * 3.2)
    col = C["night_text"] if night else C["sun"]
    halo.add_color_stop_rgba(0, *col, 0.35)
    halo.add_color_stop_rgba(1, *col, 0.0)
    ctx.set_source(halo)
    ctx.arc(x, y, r * 3.2, 0, 2 * math.pi)
    ctx.fill()
    ctx.arc(x, y, r, 0, 2 * math.pi)
    outline_fill(ctx, col, width=OUTLINE * 0.8, a=0.95)
    if not night:  # the sun disc's rays, as in Egyptian painting (thin lines down toward the land)
        rgb(ctx, C["gold"], 0.35)
        ctx.set_line_width(2)
        for k in range(-5, 6):
            a = math.pi / 2 + k * 0.12
            ctx.move_to(x + math.cos(a) * (r + 14), y + math.sin(a) * (r + 14))
            ctx.line_to(x + math.cos(a) * (r + 120), y + math.sin(a) * (r + 120))
            ctx.stroke()


def _pyramid(ctx: cairo.Context, cx: float, base_y: float, w: float, h: float) -> None:
    apex = (cx + w * 0.08, base_y - h)
    ctx.move_to(cx - w / 2, base_y)
    ctx.line_to(*apex)
    ctx.line_to(cx + w * 0.18, base_y)
    ctx.close_path()
    outline_fill(ctx, C["stone_lit"], width=OUTLINE * 0.7)
    ctx.move_to(cx + w * 0.18, base_y)
    ctx.line_to(*apex)
    ctx.line_to(cx + w / 2, base_y)
    ctx.close_path()
    outline_fill(ctx, C["stone_shade"], width=OUTLINE * 0.7)
    rgb(ctx, C["ink"], 0.12)  # faint course lines
    ctx.set_line_width(1.5)
    for i in range(1, 7):
        yy = base_y - h * i / 7
        f = 1 - i / 7
        ctx.move_to(cx - w / 2 * f + w * 0.08 * (1 - f), yy)
        ctx.line_to(cx + w / 2 * f + w * 0.08 * (1 - f), yy)
        ctx.stroke()


def _dune(ctx: cairo.Context, y0: float, amp: float, freq: float, phase: float, col) -> None:
    ctx.move_to(0, H)
    for x in range(0, W + 20, 20):
        ctx.line_to(x, y0 - amp * math.sin(x * freq + phase) - amp * 0.4 * math.sin(x * freq * 2.7 + phase))
    ctx.line_to(W, H)
    ctx.close_path()
    outline_fill(ctx, col, width=OUTLINE * 0.6)


def _palm(ctx: cairo.Context, x: float, base: float, h: float) -> None:
    ctx.move_to(x - 7, base)
    ctx.curve_to(x - 4, base - h * 0.5, x + 6, base - h * 0.8, x + 10, base - h)
    ctx.line_to(x + 22, base - h)
    ctx.curve_to(x + 16, base - h * 0.8, x + 8, base - h * 0.5, x + 9, base)
    ctx.close_path()
    outline_fill(ctx, C["bronze"], width=OUTLINE * 0.6)
    tx, ty = x + 16, base - h
    for k in range(7):
        a = math.pi + k * (math.pi / 6) + 0.05
        ln = h * 0.62
        ex, ey = tx + math.cos(a) * ln, ty + math.sin(a) * ln * 0.55 + ln * 0.25
        ctx.move_to(tx, ty)
        ctx.curve_to(tx + math.cos(a) * ln * 0.4, ty - ln * 0.25, ex, ey - ln * 0.15, ex, ey)
        ctx.curve_to(ex - 6, ey + 10, tx + math.cos(a) * ln * 0.3, ty, tx, ty + 6)
        ctx.close_path()
        outline_fill(ctx, C["olive"], width=OUTLINE * 0.5)


def _column(ctx: cairo.Context, x: float, w: float) -> None:
    top, bottom = 70, H - 40
    # shaft with flutes
    ctx.rectangle(x, top + 120, w, bottom - top - 120)
    outline_fill(ctx, C["column"])
    rgb(ctx, C["ink"], 0.25)
    ctx.set_line_width(2)
    for k in range(1, 5):
        xx = x + w * k / 5
        ctx.move_to(xx, top + 190)
        ctx.line_to(xx, bottom - 10)
        ctx.stroke()
    # painted bands under the capital
    band_cols = [C["terracotta"], C["gold"], C["indigo"], C["gold"], C["olive"]]
    by = top + 120
    for col in band_cols:
        ctx.rectangle(x, by, w, 14)
        outline_fill(ctx, col, width=2.5)
        by += 14
    # open lotus capital
    ctx.move_to(x, top + 120)
    ctx.curve_to(x - 10, top + 80, x - 34, top + 50, x - 30, top + 22)
    ctx.line_to(x + w + 30, top + 22)
    ctx.curve_to(x + w + 34, top + 50, x + w + 10, top + 80, x + w, top + 120)
    ctx.close_path()
    outline_fill(ctx, C["olive"])
    for k in range(5):  # petals
        px = x - 22 + (w + 44) * (k + 0.5) / 5
        ctx.move_to(px, top + 26)
        ctx.curve_to(px - 16, top + 60, px - 6, top + 100, px, top + 116)
        ctx.curve_to(px + 6, top + 100, px + 16, top + 60, px, top + 26)
        ctx.close_path()
        outline_fill(ctx, C["papyrus"] if k % 2 else C["gold"], width=2.5)
    # abacus block
    ctx.rectangle(x - 6, top, w + 12, 24)
    outline_fill(ctx, C["column"], width=3.5)


def _frieze(ctx: cairo.Context) -> None:
    """Painted khekher-style frieze along the top: rounded shapes in alternating earth colours."""
    y, h = 0, 64
    ctx.rectangle(0, y, W, h)
    outline_fill(ctx, C["papyrus_dark"], width=3)
    cols = [C["terracotta"], C["indigo"], C["olive"]]
    step = 40
    for i, x in enumerate(range(6, W, step)):
        ctx.move_to(x, h - 6)
        ctx.line_to(x, 20)
        ctx.curve_to(x, 6, x + 26, 6, x + 26, 20)
        ctx.line_to(x + 26, h - 6)
        ctx.close_path()
        outline_fill(ctx, cols[i % 3], width=2.5)
        diamond(ctx, x + 13, 28, 4, C["gold"])
    ctx.rectangle(0, h, W, 6)
    outline_fill(ctx, C["gold"], width=2)


def _zigzag(ctx: cairo.Context) -> None:
    y = H - 40
    ctx.rectangle(0, y, W, 40)
    outline_fill(ctx, C["papyrus_dark"], width=3)
    rgb(ctx, C["terracotta"])
    step = 36
    for x in range(0, W + step, step):
        ctx.move_to(x, y + 34)
        ctx.line_to(x + step / 2, y + 8)
        ctx.line_to(x + step, y + 34)
        ctx.close_path()
        ctx.fill()
    rgb(ctx, C["ink"])
    ctx.set_line_width(3)
    ctx.move_to(0, y)
    ctx.line_to(W, y)
    ctx.stroke()


def background(ctx: cairo.Context, *, night: bool = False, columns: bool = True, ground: bool = True) -> None:
    """Draw the full Egyptian environment. Cache it with core.cached() and blit per frame."""
    _sky(ctx, night)
    _sun(ctx, night)
    _pyramid(ctx, 1240, HORIZON + 10, 560, 300)
    _pyramid(ctx, 1640, HORIZON + 14, 340, 180)
    _pyramid(ctx, 420, HORIZON + 12, 300, 150)
    _dune(ctx, HORIZON + 20, 10, 0.004, 0.6, C["dune_far"])
    _palm(ctx, 300, HORIZON + 30, 150)
    _palm(ctx, 1500, HORIZON + 34, 120)
    if ground:
        _dune(ctx, HORIZON + 95, 14, 0.0032, 2.1, C["dune_mid"])
        _dune(ctx, HORIZON + 170, 8, 0.0024, 4.0, C["ground"])
    if night:
        ctx.rectangle(0, 0, W, H)
        rgb(ctx, C["night_bg"], 0.45)
        ctx.fill()
    frame(ctx, columns=columns)


def frame(ctx: cairo.Context, *, columns: bool = True) -> None:
    """The temple frame alone: lotus columns, top frieze and bottom band. Every scene keeps it."""
    if columns:
        _column(ctx, 34, 110)
        _column(ctx, W - 144, 110)
    _frieze(ctx)
    _zigzag(ctx)


def space(ctx: cairo.Context) -> None:
    """Night sky seen through the temple frame: deep umber-black, fixed stars, then the frame."""
    import random
    g = cairo.RadialGradient(W / 2, H / 2, 100, W / 2, H / 2, W * 0.7)
    g.add_color_stop_rgb(0, *mix(C["night_bg"], C["indigo"], 0.22))
    g.add_color_stop_rgb(1, *C["night_bg"])
    ctx.set_source(g)
    ctx.paint()
    rnd = random.Random(11)
    for _ in range(420):
        x, y, r = rnd.uniform(0, W), rnd.uniform(60, H - 40), rnd.choice((0.8, 1.0, 1.3, 1.8))
        rgb(ctx, C["night_text"], rnd.uniform(0.25, 0.85))
        ctx.arc(x, y, r, 0, 2 * math.pi)
        ctx.fill()
    frame(ctx)


def panel(ctx: cairo.Context, x: float, y: float, w: float, h: float, a: float = 1.0) -> None:
    """A papyrus sheet with an umber border and a gold inner rule, for text-heavy cards."""
    from .core import rounded_rect
    ctx.save()
    rounded_rect(ctx, x + 8, y + 10, w, h, 10)
    rgb(ctx, C["ink"], 0.18 * a)
    ctx.fill()
    rounded_rect(ctx, x, y, w, h, 10)
    outline_fill(ctx, C["papyrus"], a=a)
    rounded_rect(ctx, x + 16, y + 16, w - 32, h - 32, 6)
    rgb(ctx, C["gold"], a)
    ctx.set_line_width(2.2)
    ctx.stroke()
    ctx.restore()
