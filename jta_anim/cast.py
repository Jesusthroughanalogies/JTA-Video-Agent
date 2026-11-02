"""The recurring cast, drawn to match the AI footage (system prompt 5.2 and 5.5).

Thick umber outlines and flat colours, as in the reels, with adult proportions so they read as
the same people as in the AI clips. Every function draws a figure standing on (x, feet_y) at
height h (top of head to soles). Never improvise a character outside this file.

- jesus(): matches the JTA-Jesus element. Off-white ankle-length tunic, rope belt, dark brown wool
  mantle over both shoulders to the calves, shoulder-length wavy dark brown hair, brown sandals.
  Shown from behind or by His hands only; there is no front view with a face, by design.
- seeker(): the grey-robed man of the Ep 1 AI shots. Plain grey wool robe, short dark hair, short
  dark beard. Front and back views.
- crowd_figure(): simple figures in dyed robes; never off-white with a brown mantle.
"""
from __future__ import annotations

import math

import cairo

from .core import outline_fill, rgb
from .theme import C, OUTLINE


def _ellipse(ctx: cairo.Context, x: float, y: float, rx: float, ry: float) -> None:
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(rx, ry)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()


def _feet(ctx, x, fy, u, step, col_strap):
    for side, off in ((-1, -step), (1, step)):
        fx = x + side * 3.6 * u
        _ellipse(ctx, fx, fy - 1.6 * u + off * u * 0.4, 3.0 * u, 1.9 * u)
        outline_fill(ctx, C["skin"], width=OUTLINE * 0.7)
        ctx.rectangle(fx - 3.0 * u, fy - 0.6 * u + off * u * 0.4, 6.0 * u, 0.9 * u)
        outline_fill(ctx, C["sandal"], width=OUTLINE * 0.5)
        ctx.move_to(fx - 2.6 * u, fy - 2.4 * u + off * u * 0.4)
        ctx.line_to(fx + 2.6 * u, fy - 2.4 * u + off * u * 0.4)
        rgb(ctx, col_strap)
        ctx.set_line_width(0.8 * u)
        ctx.stroke()


def jesus(ctx: cairo.Context, x: float, fy: float, h: float, *, step: float = 0.0, sway: float = 0.0,
          alpha: float = 1.0, reach: float = 0.0) -> None:
    """Jesus seen from behind. step (-1..1) shifts the feet for a walk cycle; sway tilts gently.
    reach (0..1) lifts His right hand out to the side and back, open, an invitation to the viewer."""
    u = h / 100
    ctx.save()
    ctx.push_group()
    ctx.translate(x, fy)
    ctx.rotate(sway * 0.02)
    ctx.translate(-x, -fy)
    _feet(ctx, x, fy, u, step, C["sandal"])
    # tunic (visible below the mantle and at the sides)
    ctx.move_to(x - 11 * u, fy - 80 * u)
    ctx.curve_to(x - 13 * u, fy - 50 * u, x - 15 * u, fy - 25 * u, x - 15.5 * u, fy - 5 * u)
    ctx.curve_to(x - 5 * u, fy - 3.5 * u, x + 5 * u, fy - 3.5 * u, x + 15.5 * u, fy - 5 * u)
    ctx.curve_to(x + 15 * u, fy - 25 * u, x + 13 * u, fy - 50 * u, x + 11 * u, fy - 80 * u)
    ctx.close_path()
    outline_fill(ctx, C["jesus_tunic"])
    # hands at the sides (the right one is drawn later when reaching)
    for side in ((-1,) if reach > 0.02 else (-1, 1)):
        _ellipse(ctx, x + side * 15.2 * u, fy - 45 * u, 2.1 * u, 2.8 * u)
        outline_fill(ctx, C["skin"], width=OUTLINE * 0.7)
    # rope belt ends showing at the sides
    for side in (-1, 1):
        ctx.move_to(x + side * 12.8 * u, fy - 52 * u)
        ctx.line_to(x + side * 13.8 * u, fy - 52 * u)
        rgb(ctx, C["rope"])
        ctx.set_line_width(1.6 * u)
        ctx.stroke()
    # mantle: over both shoulders and hanging down each side to the calves, with the off-white
    # tunic showing as a strip down the middle of the back (as in the AI footage)
    for side in (-1, 1):
        ctx.move_to(x + side * 3.5 * u, fy - 84 * u)
        ctx.curve_to(x + side * 9 * u, fy - 85 * u, x + side * 13 * u, fy - 83 * u, x + side * 13.5 * u, fy - 79 * u)
        ctx.curve_to(x + side * 15 * u, fy - 60 * u, x + side * 14.5 * u, fy - 40 * u, x + side * 13.6 * u, fy - 23 * u)
        ctx.curve_to(x + side * 9 * u, fy - 20.5 * u, x + side * 5 * u, fy - 21 * u, x + side * 2.6 * u, fy - 22.5 * u)
        ctx.curve_to(x + side * 3.2 * u, fy - 45 * u, x + side * 2.4 * u, fy - 65 * u, x + side * 3.5 * u, fy - 84 * u)
        ctx.close_path()
        outline_fill(ctx, C["jesus_mantle"])
        rgb(ctx, C["ink"], 0.45)  # wool folds
        ctx.set_line_width(1.1 * u)
        for f in (7.5, 11):
            ctx.move_to(x + side * f * u, fy - 76 * u)
            ctx.curve_to(x + side * (f + 0.5) * u, fy - 55 * u, x + side * (f + 1) * u, fy - 40 * u,
                         x + side * (f + 0.6) * u, fy - 25 * u)
            ctx.stroke()
    # hood, bunched at the neck
    _ellipse(ctx, x, fy - 79.5 * u, 8.2 * u, 3.6 * u)
    outline_fill(ctx, C["jesus_mantle"], width=OUTLINE * 0.8)
    # hair: shoulder-length, wavy, covering the head from behind
    ctx.move_to(x - 7 * u, fy - 93 * u)
    ctx.curve_to(x - 9 * u, fy - 101 * u, x + 9 * u, fy - 101 * u, x + 7 * u, fy - 93 * u)
    ctx.curve_to(x + 9.5 * u, fy - 86 * u, x + 8 * u, fy - 80 * u, x + 9 * u, fy - 75 * u)
    for k in range(5):  # wavy ends
        xa = x + (9 - (k + 1) * 3.6) * u
        ctx.curve_to(xa + 2.6 * u, fy - 72.5 * u, xa + 1.0 * u, fy - 72.5 * u, xa, fy - 75.5 * u)
    ctx.curve_to(x - 8 * u, fy - 80 * u, x - 9.5 * u, fy - 86 * u, x - 7 * u, fy - 93 * u)
    ctx.close_path()
    outline_fill(ctx, C["jesus_hair"])
    rgb(ctx, C["sandal"], 0.55)  # strands
    ctx.set_line_width(0.8 * u)
    for k in (-4, 0, 4):
        ctx.move_to(x + k * 0.8 * u, fy - 97 * u)
        ctx.curve_to(x + k * u, fy - 88 * u, x + k * 1.3 * u, fy - 82 * u, x + k * 1.5 * u, fy - 77 * u)
        ctx.stroke()
    if reach > 0.02:  # right arm: off-white sleeve out from under the mantle, open hand
        sx, sy = x + 12.5 * u, fy - 74 * u
        hx = x + (15.2 + 16 * reach) * u
        hy = fy - (45 + 17 * reach) * u
        for col, wdt in ((C["ink"], 5.2 * u + OUTLINE), (C["jesus_tunic"], 5.2 * u)):
            ctx.move_to(sx, sy)
            ctx.curve_to(sx + 4 * u * reach, sy + 8 * u, hx - 4 * u, hy - 6 * u * reach, hx - 1 * u, hy - 1 * u)
            rgb(ctx, col)
            ctx.set_line_width(wdt)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.stroke()
        _ellipse(ctx, hx + 1.2 * u, hy + 0.5 * u, 2.4 * u, 3.0 * u)
        outline_fill(ctx, C["skin"], width=OUTLINE * 0.7)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def jesus_hands(ctx: cairo.Context, x: float, y: float, s: float, *, open_: float = 0.0) -> None:
    """Close-up of His hands breaking a round flatbread, seen over the shoulder, off-white sleeves
    with the brown mantle at the edges. open_ (0..1) pulls the bread apart."""
    u = s / 100
    for side in (-1, 1):
        hx = x + side * (16 + 22 * open_) * u
        hy = y + 8 * u
        sx, sy = x + side * 46 * u, y + 62 * u   # where the arm enters the frame
        for col, wdt in ((C["ink"], 24 * u), (C["jesus_tunic"], 24 * u - 2 * OUTLINE)):
            ctx.move_to(sx, sy)
            ctx.curve_to(sx - side * 8 * u, sy - 30 * u, hx + side * 14 * u, hy + 34 * u, hx + side * 6 * u, hy + 14 * u)
            rgb(ctx, col)
            ctx.set_line_width(wdt)
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            ctx.stroke()
    for side in (-1, 1):  # bread halves
        bx = x + side * (3 + 22 * open_) * u
        a0, a1 = (-math.pi / 2, math.pi / 2) if side > 0 else (math.pi / 2, 3 * math.pi / 2)
        ctx.move_to(bx, y - 22 * u)
        ctx.arc(bx, y, 22 * u, a0, a1)
        ctx.close_path()
        outline_fill(ctx, C["bronze_light"])
        rgb(ctx, C["bronze"], 0.6)  # baked spots
        for k in range(3):
            ctx.arc(bx + side * (7 + k * 4) * u, y + (-8 + k * 7) * u, 1.6 * u, 0, 2 * math.pi)
            ctx.fill()
    for side in (-1, 1):  # hands gripping the bread
        hx = x + side * (16 + 22 * open_) * u
        _ellipse(ctx, hx + side * 4 * u, y + 10 * u, 9 * u, 11 * u)
        outline_fill(ctx, C["skin"])
        _ellipse(ctx, hx - side * 3 * u, y - 4 * u, 3.4 * u, 6 * u)   # thumb over the bread
        outline_fill(ctx, C["skin"], width=OUTLINE * 0.7)


def seeker(ctx: cairo.Context, x: float, fy: float, h: float, *, view: str = "front", step: float = 0.0,
           look_up: float = 0.0, alpha: float = 1.0, shrug: float = 0.0, robe: str = "seeker_robe") -> None:
    """The Seeker: plain grey wool robe, short dark hair, short dark beard. view 'front' or 'back'."""
    u = h / 100
    ctx.save()
    ctx.push_group()
    _feet(ctx, x, fy, u, step, C["sandal"])
    # robe
    ctx.move_to(x - 11 * u, fy - 80 * u)
    ctx.curve_to(x - 13.5 * u, fy - 50 * u, x - 15 * u, fy - 25 * u, x - 15 * u, fy - 5 * u)
    ctx.curve_to(x - 5 * u, fy - 3.5 * u, x + 5 * u, fy - 3.5 * u, x + 15 * u, fy - 5 * u)
    ctx.curve_to(x + 15 * u, fy - 25 * u, x + 13.5 * u, fy - 50 * u, x + 11 * u, fy - 80 * u)
    ctx.curve_to(x + 5 * u, fy - 84 * u, x - 5 * u, fy - 84 * u, x - 11 * u, fy - 80 * u)
    ctx.close_path()
    outline_fill(ctx, C[robe])
    rgb(ctx, C["seeker_robe_shade"] if robe == "seeker_robe" else C["ink"], 1.0 if robe == "seeker_robe" else 0.18)
    ctx.move_to(x + 8 * u, fy - 78 * u)
    ctx.curve_to(x + 11 * u, fy - 50 * u, x + 12 * u, fy - 25 * u, x + 12 * u, fy - 6 * u)
    ctx.line_to(x + 14.6 * u, fy - 5.5 * u)
    ctx.curve_to(x + 14.6 * u, fy - 25 * u, x + 13 * u, fy - 50 * u, x + 10.6 * u, fy - 79 * u)
    ctx.close_path()
    ctx.fill()
    # cord belt
    ctx.move_to(x - 13.2 * u, fy - 53 * u)
    ctx.line_to(x + 13.2 * u, fy - 53 * u)
    rgb(ctx, C["ink"])
    ctx.set_line_width(1.4 * u)
    ctx.stroke()
    # hands (a shrug lifts the forearms out to the sides, palms up)
    for side in (-1, 1):
        if shrug > 0.02:
            ex, ey = x + side * 14 * u, fy - 60 * u
            hx, hy_ = x + side * (15 + 9 * shrug) * u, fy - (46 + 20 * shrug) * u
            for col, wdt in ((C["ink"], 4.6 * u + OUTLINE), (C[robe], 4.6 * u)):
                ctx.move_to(ex, ey)
                ctx.line_to(hx, hy_)
                rgb(ctx, col)
                ctx.set_line_width(wdt)
                ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                ctx.stroke()
            _ellipse(ctx, hx + side * 1.5 * u, hy_ - 1.2 * u, 2.6 * u, 1.9 * u)
        else:
            _ellipse(ctx, x + side * 15 * u, fy - 46 * u, 2.1 * u, 2.7 * u)
        outline_fill(ctx, C["skin"], width=OUTLINE * 0.7)
    # head
    hy = fy - 89 * u - look_up * 0.6 * u - shrug * 2.5 * u
    if view == "front":
        _ellipse(ctx, x, hy, 6.6 * u, 7.8 * u)
        outline_fill(ctx, C["skin"])
        # short beard
        ctx.move_to(x - 6.2 * u, hy + 0.5 * u)
        ctx.curve_to(x - 6 * u, hy + 9 * u, x + 6 * u, hy + 9 * u, x + 6.2 * u, hy + 0.5 * u)
        ctx.curve_to(x + 3 * u, hy + 4 * u, x - 3 * u, hy + 4 * u, x - 6.2 * u, hy + 0.5 * u)
        ctx.close_path()
        outline_fill(ctx, C["seeker_hair"], width=OUTLINE * 0.6)
        # short hair
        ctx.move_to(x - 6.8 * u, hy - 1 * u)
        ctx.curve_to(x - 8 * u, hy - 10 * u, x + 8 * u, hy - 10 * u, x + 6.8 * u, hy - 1 * u)
        ctx.curve_to(x + 4 * u, hy - 5.5 * u, x - 4 * u, hy - 5.5 * u, x - 6.8 * u, hy - 1 * u)
        ctx.close_path()
        outline_fill(ctx, C["seeker_hair"], width=OUTLINE * 0.6)
        # simple face, as in the reels
        rgb(ctx, C["ink"])
        for side in (-1, 1):
            ctx.arc(x + side * 2.4 * u, hy - 0.6 * u - look_up * 0.5 * u, 0.75 * u, 0, 2 * math.pi)
            ctx.fill()
            ctx.move_to(x + side * 1.4 * u, hy - 2.9 * u)
            ctx.line_to(x + side * 3.6 * u, hy - 3.2 * u)
            ctx.set_line_width(0.6 * u)
            ctx.stroke()
    else:
        _ellipse(ctx, x, hy, 6.6 * u, 7.8 * u)
        outline_fill(ctx, C["seeker_hair"])
        rgb(ctx, C["skin"])  # neck
        ctx.rectangle(x - 3 * u, hy + 6.4 * u, 6 * u, 2.4 * u)
        ctx.fill()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


CROWD_ROBES = ("terracotta", "olive", "indigo", "gold", "bronze")


def crowd_figure(ctx: cairo.Context, x: float, fy: float, h: float, robe: str = "terracotta",
                 alpha: float = 1.0) -> None:
    """A simple background figure in a dyed robe (never off-white with a brown mantle)."""
    assert robe in CROWD_ROBES
    u = h / 100
    ctx.save()
    ctx.push_group()
    ctx.move_to(x - 10 * u, fy - 78 * u)
    ctx.curve_to(x - 13 * u, fy - 40 * u, x - 14 * u, fy - 20 * u, x - 14 * u, fy - 2 * u)
    ctx.line_to(x + 14 * u, fy - 2 * u)
    ctx.curve_to(x + 14 * u, fy - 20 * u, x + 13 * u, fy - 40 * u, x + 10 * u, fy - 78 * u)
    ctx.close_path()
    outline_fill(ctx, C[robe])
    _ellipse(ctx, x, fy - 87 * u, 6.4 * u, 7.6 * u)
    outline_fill(ctx, C["skin"])
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def archer(ctx: cairo.Context, x: float, fy: float, h: float, *, robe: str = "terracotta", draw: float = 0.0,
           alpha: float = 1.0) -> None:
    """An ancient archer facing the viewer: dyed tunic, leather cap, a recurve bow held across the body.
    draw (0..1) pulls the string back toward the chest. Never off-white with a brown mantle."""
    assert robe in CROWD_ROBES
    u = h / 100
    ctx.save()
    ctx.push_group()
    crowd_figure(ctx, x, fy, h, robe)
    _ellipse(ctx, x, fy - 92 * u, 6.8 * u, 4.2 * u)  # leather cap
    outline_fill(ctx, C["bronze"], width=OUTLINE * 0.6)
    bx, by = x - 4 * u, fy - 58 * u                    # bow, held upright in front
    ctx.move_to(bx - 2 * u, by - 30 * u)
    ctx.curve_to(bx - 12 * u, by - 14 * u, bx - 12 * u, by + 14 * u, bx - 2 * u, by + 30 * u)
    rgb(ctx, C["ink"])
    ctx.set_line_width(3.0 * u)
    ctx.stroke()
    sx = bx - 2 * u + 9 * u * draw                     # string
    ctx.move_to(bx - 2 * u, by - 30 * u)
    ctx.line_to(sx, by)
    ctx.line_to(bx - 2 * u, by + 30 * u)
    ctx.set_line_width(0.8 * u)
    ctx.stroke()
    ctx.move_to(sx, by)                                # arrow on the string
    ctx.line_to(bx - 16 * u, by)
    ctx.set_line_width(1.2 * u)
    ctx.stroke()
    _ellipse(ctx, sx + 1 * u, by, 2.4 * u, 2.6 * u)    # drawing hand
    outline_fill(ctx, C["skin"], width=OUTLINE * 0.5)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()
