"""Reusable props for the analogies: dominoes, bronze dials, galaxies, atoms, the three picture
frames, the sunrise painting, small icons and the scripture card. Earth palette, thick outlines."""
from __future__ import annotations

import math
import random

import cairo

from .core import (clamp, diamond, ease_out, label, lerp, outline_fill, ramp, rgb, rounded_rect, text,
                   text_width)
from .theme import C, OUTLINE, W

# ---------------------------------------------------------------- helpers


def glow(ctx, x, y, r, col, a):
    if a <= 0:
        return
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, *col, a)
    g.add_color_stop_rgba(1, *col, 0)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.fill()


def ellipse(ctx, x, y, rx, ry):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(max(rx, 0.01), max(ry, 0.01))
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()


def tick(ctx, x, y, s, p, col=C["olive"]):
    """A hand-drawn tick that draws on with p (0..1)."""
    if p <= 0:
        return
    pts = [(x - s * 0.5, y), (x - s * 0.12, y + s * 0.4), (x + s * 0.6, y - s * 0.5)]
    l1 = math.dist(pts[0], pts[1])
    l2 = math.dist(pts[1], pts[2])
    d = (l1 + l2) * clamp(p)
    ctx.move_to(*pts[0])
    if d <= l1:
        ctx.line_to(lerp(pts[0][0], pts[1][0], d / l1), lerp(pts[0][1], pts[1][1], d / l1))
    else:
        ctx.line_to(*pts[1])
        k = (d - l1) / l2
        ctx.line_to(lerp(pts[1][0], pts[2][0], k), lerp(pts[1][1], pts[2][1], k))
    rgb(ctx, col)
    ctx.set_line_width(s * 0.16)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.stroke()


def arrow(ctx, x0, y0, x1, y1, col=C["ink"], width=5.0, head=18, a=1.0, p=1.0):
    """Straight arrow drawing on with p."""
    if p <= 0:
        return
    xe, ye = lerp(x0, x1, p), lerp(y0, y1, p)
    ctx.move_to(x0, y0)
    ctx.line_to(xe, ye)
    rgb(ctx, col, a)
    ctx.set_line_width(width)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.stroke()
    ang = math.atan2(ye - y0, xe - x0)
    ctx.move_to(xe, ye)
    ctx.line_to(xe - head * math.cos(ang - 0.45), ye - head * math.sin(ang - 0.45))
    ctx.line_to(xe - head * math.cos(ang + 0.45), ye - head * math.sin(ang + 0.45))
    ctx.close_path()
    ctx.fill()


def fit_lines(ctx, s, size, max_w, italic=False):
    lines, cur = [], []
    for w in s.split():
        trial = " ".join(cur + [w])
        if cur and text_width(ctx, trial, size, italic=italic) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- dominoes

DOM_W, DOM_H = 46, 150


def domino(ctx, x, base, angle, *, s=1.0, glow_a=0.0, alpha=1.0):
    """A limestone domino whose bottom-right corner sits at (x + w, base); angle tips it right."""
    w, h = DOM_W * s, DOM_H * s
    ctx.save()
    ctx.translate(x + w, base)
    ctx.rotate(angle)
    ctx.translate(-w, 0)
    if glow_a:
        glow(ctx, w / 2, -h / 2, 170 * s, C["gold"], 0.55 * glow_a)
    ctx.push_group()
    rounded_rect(ctx, 0, -h, w, h, 8 * s)
    outline_fill(ctx, C["limestone"], width=OUTLINE * max(s, 0.5))
    ctx.move_to(6 * s, -h / 2)
    ctx.line_to(w - 6 * s, -h / 2)
    rgb(ctx, C["ink"])
    ctx.set_line_width(2.5 * s)
    ctx.stroke()
    for px, py in ((0.5, 0.25), (0.3, 0.68), (0.7, 0.82)):
        ctx.arc(w * px, -h * py, 4.2 * s, 0, 2 * math.pi)
        ctx.fill()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def domino_rest(gap=100, s=1.0):
    """Angle at which a domino leans on its neighbour."""
    return math.asin(clamp((gap - DOM_W * s) / (DOM_H * s), 0, 1))


def domino_line(ctx, x0, base, n, gap, angles, *, s=1.0, alphas=None, glows=None):
    for i in range(n):
        domino(ctx, x0 + i * gap, base, angles[i], s=s, alpha=alphas[i] if alphas else 1.0,
               glow_a=glows[i] if glows else 0.0)


def ledge(ctx, x, y, w):
    ctx.rectangle(x, y, w, 26)
    outline_fill(ctx, C["stone_shade"])


# ---------------------------------------------------------------- bronze dials

BAND = (math.radians(268), math.radians(275))   # the thin gold "life" band near the top
BAND_MID = (BAND[0] + BAND[1]) / 2


def dial(ctx, cx, cy, r, needle, *, band=True, alpha=1.0, warn=0.0):
    ctx.new_path()
    ctx.save()
    ctx.push_group()
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    outline_fill(ctx, C["bronze"])
    g = cairo.RadialGradient(cx - r * 0.3, cy - r * 0.3, r * 0.1, cx, cy, r * 0.85)
    g.add_color_stop_rgb(0, *C["bronze_light"])
    g.add_color_stop_rgb(1, *C["bronze_face"])
    ctx.arc(cx, cy, r * 0.84, 0, 2 * math.pi)
    ctx.set_source(g)
    ctx.fill_preserve()
    rgb(ctx, C["ink"])
    ctx.set_line_width(OUTLINE * 0.7)
    ctx.stroke()
    for k in range(0, 31):
        a = math.radians(200 + k * 140 / 30)
        r0 = r * (0.62 if k % 5 == 0 else 0.68)
        ctx.move_to(cx + math.cos(a) * r0, cy + math.sin(a) * r0)
        ctx.line_to(cx + math.cos(a) * r * 0.76, cy + math.sin(a) * r * 0.76)
        rgb(ctx, C["ink"], 0.8)
        ctx.set_line_width(2.4 if k % 5 == 0 else 1.4)
        ctx.stroke()
    if band:
        ctx.arc(cx, cy, r * 0.70, *BAND)
        rgb(ctx, C["gold"])
        ctx.set_line_width(r * 0.13)
        ctx.stroke()
    if warn:
        glow(ctx, cx, cy, r * 1.1, C["terracotta"], 0.35 * warn)
    ctx.move_to(cx + math.cos(needle + math.pi / 2) * r * 0.04, cy + math.sin(needle + math.pi / 2) * r * 0.04)
    ctx.line_to(cx + math.cos(needle) * r * 0.74, cy + math.sin(needle) * r * 0.74)
    ctx.line_to(cx + math.cos(needle - math.pi / 2) * r * 0.04, cy + math.sin(needle - math.pi / 2) * r * 0.04)
    ctx.close_path()
    outline_fill(ctx, C["ink"], width=2)
    ctx.arc(cx, cy, r * 0.08, 0, 2 * math.pi)
    outline_fill(ctx, C["gold"], width=3)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


# ---------------------------------------------------------------- cosmos

def galaxy(ctx, x, y, r, rot=0.0, a=1.0, seed=0):
    if a <= 0 or r <= 0.5:
        return
    glow(ctx, x, y, r * 1.4, C["night_text"], 0.35 * a)
    glow(ctx, x, y, r * 0.35, C["sun"], 0.9 * a)
    rnd = random.Random(seed)
    n = max(6, int(r * 1.6))
    for arm in (0, math.pi):
        for i in range(n):
            k = i / n
            ang = rot + arm + k * 3.4 + rnd.uniform(-0.25, 0.25)
            rr = r * (0.15 + k * 0.85)
            px, py = x + math.cos(ang) * rr, y + math.sin(ang) * rr * 0.55
            rgb(ctx, C["night_text"] if rnd.random() > 0.3 else C["sun"], a * (1 - k * 0.6))
            ctx.arc(px, py, max(0.8, r * 0.04 * (1 - k * 0.5)), 0, 2 * math.pi)
            ctx.fill()


def atom(ctx, x, y, r, t, a=1.0, spread=0.0, electrons=3, seed=0, orbit=None, nucleus=0.1):
    """A simple atom: nucleus and orbiting electrons. spread (0..1) flies the parts apart."""
    if a <= 0:
        return
    rnd = random.Random(seed)
    for k in range(3):  # orbits
        if spread < 0.5:
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(k * math.pi / 3)
            ellipse(ctx, 0, 0, r, r * 0.38)
            ctx.restore()
            rgb(ctx, orbit or C["night_text"], (0.8 if orbit else 0.5) * a * (1 - spread * 2))
            ctx.set_line_width(3 if orbit else 2)
            ctx.stroke()
    for i in range(6):  # nucleus
        ang = rnd.uniform(0, 2 * math.pi)
        d = r * 0.12 + spread * r * rnd.uniform(1.5, 3.5)
        ctx.arc(x + math.cos(ang + i) * d, y + math.sin(ang + i) * d, r * nucleus, 0, 2 * math.pi)
        outline_fill(ctx, C["terracotta"] if i % 2 else C["stone_lit"], width=2, a=a)
    for k in range(electrons):
        ang = t * 2.2 + k * 2 * math.pi / electrons
        ex, ey = math.cos(ang) * r, math.sin(ang) * r * 0.38
        rot = k * math.pi / 3
        px = x + ex * math.cos(rot) - ey * math.sin(rot)
        py = y + ex * math.sin(rot) + ey * math.cos(rot)
        fly = spread * r * 3.0
        px += math.cos(rot + k) * fly
        py += math.sin(rot + k) * fly
        glow(ctx, px, py, r * 0.18, C["gold"], 0.6 * a)
        ctx.arc(px, py, r * 0.06, 0, 2 * math.pi)
        if orbit:
            outline_fill(ctx, C["gold"], width=2.5, a=a)
        else:
            rgb(ctx, C["gold"], a)
            ctx.fill()


# ---------------------------------------------------------------- the three picture frames

def picture_frame(ctx, cx, cy, w, h, *, lit=0.0, alpha=1.0, scale=1.0):
    """A carved wooden frame with a papyrus face. lit (0..1) adds a gold border and glow."""
    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(scale, scale)
    if lit:
        glow(ctx, 0, 0, max(w, h) * 0.85, C["gold"], 0.45 * lit * alpha)
    ctx.push_group()
    rounded_rect(ctx, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 8)
    outline_fill(ctx, C["bronze"])
    rounded_rect(ctx, -w / 2, -h / 2, w, h, 4)
    outline_fill(ctx, C["papyrus"], width=3.5)
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        diamond(ctx, dx * (w / 2 + 11), dy * (h / 2 + 11), 6, C["gold"])
    if lit:
        rounded_rect(ctx, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 8)
        rgb(ctx, C["gold"], lit)
        ctx.set_line_width(7)
        ctx.stroke()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def icon_domino(ctx, cx, cy, s, a=1.0, glow_a=0.0):
    domino(ctx, cx - DOM_W * s / 2, cy + DOM_H * s / 2, 0.0, s=s, alpha=a, glow_a=glow_a)


def icon_dial(ctx, cx, cy, s, a=1.0):
    dial(ctx, cx, cy, 100 * s, BAND_MID, alpha=a)


def icon_painting(ctx, cx, cy, s, a=1.0):
    w, h = 220 * s, 150 * s
    ctx.save()
    ctx.push_group()
    sunrise(ctx, cx - w / 2, cy - h / 2, w, h)
    ctx.rectangle(cx - w / 2, cy - h / 2, w, h)
    rgb(ctx, C["ink"])
    ctx.set_line_width(3)
    ctx.stroke()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()


FRAME_SLOTS = (560, 960, 1360)
FRAME_Y, FRAME_W, FRAME_H = 470, 300, 260


def frame_icon(ctx, k, cx, cy, s=1.0, a=1.0):
    if a <= 0:
        return
    if k == 0:
        icon_domino(ctx, cx, cy, 1.1 * s, a)
    elif k == 1:
        icon_dial(ctx, cx, cy, 1.0 * s, a)
    else:
        icon_painting(ctx, cx, cy, 1.05 * s, a)


def triptych(ctx, states):
    """states: list of dicts per frame k: x, y, scale, alpha, fill (icon alpha), lit, tick, title alpha."""
    names = ("The dominoes", "The dials", "The painting")
    for k, st in enumerate(states):
        if st.get("alpha", 1) <= 0:
            continue
        x, y, sc = st.get("x", FRAME_SLOTS[k]), st.get("y", FRAME_Y), st.get("scale", 1.0)
        a = st.get("alpha", 1.0)
        picture_frame(ctx, x, y, FRAME_W, FRAME_H, lit=st.get("lit", 0.0), alpha=a, scale=sc)
        frame_icon(ctx, k, x, y, sc, a * st.get("fill", 0.0))
        if st.get("title", 0) > 0:
            text(ctx, names[k].upper(), x, y + (FRAME_H / 2 + 75) * sc, 26 * sc, C["ink"], spacing=6,
                 alpha=a * st["title"])
        if st.get("tick", 0) > 0:
            ctx.arc(x + FRAME_W / 2 * sc, y - FRAME_H / 2 * sc, 34 * sc, 0, 2 * math.pi)
            outline_fill(ctx, C["papyrus"], a=a)
            tick(ctx, x + FRAME_W / 2 * sc, y - FRAME_H / 2 * sc, 34 * sc, st["tick"])


# ---------------------------------------------------------------- the sunrise painting

def sunrise(ctx, x, y, w, h, *, sun_up=1.0, horizon=0.55):
    """The fresco of a sunrise over the sea, clipped to the rect."""
    hy = y + h * horizon
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    g = cairo.LinearGradient(0, y, 0, hy)
    g.add_color_stop_rgb(0, *C["sky_top"])
    g.add_color_stop_rgb(0.6, *C["papyrus_dark"])
    g.add_color_stop_rgb(1, *C["sun"])
    ctx.set_source(g)
    ctx.paint()
    sr = h * 0.17
    sy = hy + sr * 0.3 - sun_up * sr * 0.9
    glow(ctx, x + w * 0.5, sy, sr * 3.2, C["sun"], 0.5)
    ctx.arc(x + w * 0.5, sy, sr, 0, 2 * math.pi)
    outline_fill(ctx, C["sun"], width=max(1.5, OUTLINE * w / 1900))
    sea = cairo.LinearGradient(0, hy, 0, y + h)
    sea.add_color_stop_rgb(0, *C["indigo"])
    sea.add_color_stop_rgb(1, *C["olive"])
    ctx.rectangle(x, hy, w, h)
    ctx.set_source(sea)
    ctx.fill()
    rgb(ctx, C["sun"], 0.6)  # sun path on the water
    for i in range(6):
        yy = hy + (i + 1) * h * 0.05
        ww = w * (0.05 + i * 0.025)
        ctx.rectangle(x + w * 0.5 - ww / 2, yy, ww, max(1.0, h * 0.008))
        ctx.fill()
    # shore in the foreground (sand curving up from the right)
    ctx.move_to(x, y + h)
    ctx.line_to(x, y + h * 0.88)
    ctx.curve_to(x + w * 0.35, y + h * 0.84, x + w * 0.7, y + h * 0.80, x + w, y + h * 0.70)
    ctx.line_to(x + w, y + h)
    ctx.close_path()
    outline_fill(ctx, C["dune_mid"], width=max(1.5, OUTLINE * w / 1900))
    ctx.move_to(x, hy)
    ctx.line_to(x + w, hy)
    rgb(ctx, C["ink"], 0.8)
    ctx.set_line_width(max(1.0, 3 * w / 1900))
    ctx.stroke()
    ctx.restore()


def shore_y(x, y, w, h, fx):
    """Height of the painted shore at fraction fx across the painting."""
    # approximates the bezier in sunrise(); good enough to stand a figure on
    return y + h * (0.88 - 0.18 * fx ** 1.6)


# ---------------------------------------------------------------- little icons

def leaf(ctx, x, y, s, a=1.0):
    ctx.move_to(x, y + s)
    ctx.curve_to(x - s * 0.8, y + s * 0.2, x - s * 0.5, y - s * 0.7, x, y - s)
    ctx.curve_to(x + s * 0.5, y - s * 0.7, x + s * 0.8, y + s * 0.2, x, y + s)
    ctx.close_path()
    outline_fill(ctx, C["olive"], a=a)
    ctx.move_to(x, y + s)
    ctx.line_to(x, y - s * 0.7)
    rgb(ctx, C["ink"], a)
    ctx.set_line_width(2)
    ctx.stroke()


def heart(ctx, x, y, s, a=1.0, col=C["terracotta"]):
    ctx.move_to(x, y + s * 0.8)
    ctx.curve_to(x - s * 1.2, y - s * 0.1, x - s * 0.6, y - s * 1.0, x, y - s * 0.35)
    ctx.curve_to(x + s * 0.6, y - s * 1.0, x + s * 1.2, y - s * 0.1, x, y + s * 0.8)
    ctx.close_path()
    outline_fill(ctx, col, a=a)


def hand_icon(ctx, x, y, s, a=1.0, col=C["skin"], line=C["ink"]):
    """An open hand, palm facing the viewer."""
    rounded_rect(ctx, x - s * 0.45, y - s * 0.2, s * 0.9, s * 0.9, s * 0.3)
    outline_fill(ctx, col, line, a=a)
    for i, (dx, ln) in enumerate(((-0.33, 0.62), (-0.11, 0.78), (0.11, 0.74), (0.33, 0.6))):
        rounded_rect(ctx, x + dx * s - s * 0.1, y - s * 0.2 - ln * s, s * 0.2, ln * s + s * 0.15, s * 0.1)
        outline_fill(ctx, col, line, width=OUTLINE * 0.7, a=a)
    ctx.save()
    ctx.translate(x - s * 0.45, y + s * 0.25)
    ctx.rotate(-0.7)
    rounded_rect(ctx, -s * 0.1, -s * 0.5, s * 0.2, s * 0.55, s * 0.1)
    ctx.restore()
    outline_fill(ctx, col, line, width=OUTLINE * 0.7, a=a)


def question_mark(ctx, x, y, size, col=C["terracotta"], a=1.0, rot=0.0):
    text(ctx, "?", x, y, size, col, alpha=a, rot=rot, shadow=True)


# ---------------------------------------------------------------- scripture and quote card

def verse_card(ctx, t, verse, ref, *, gold=(), y_mid=None, panel_a=1.0, start=0.3, per_word=0.16, glow_words=False,
               size=66, max_w=1100, pw=1300):
    """Papyrus card; the verse writes on word by word, then the reference label draws in."""
    from .theme import H
    gold = {g.lower() for g in gold}
    # fit the text: shrink until it fits in 4 lines
    while True:
        lines = fit_lines(ctx, verse, size, max_w, italic=True)
        if len(lines) <= 4 or size <= 40:
            break
        size -= 4
    lh = size * 1.32
    ph = lh * len(lines) + 210
    y_mid = y_mid or H / 2 - 30
    pa = ease_out(ramp(t, 0.0, 0.5)) * panel_a
    px, py = W / 2 - pw / 2, y_mid - ph / 2 + (1 - pa / max(panel_a, 0.01)) * 40
    from .egypt import panel
    panel(ctx, px, py, pw, ph, a=pa)
    y0 = py + 95 + size * 0.6
    idx = 0
    space = text_width(ctx, " ", size, italic=True)
    for li, ln in enumerate(lines):
        lw = text_width(ctx, " ".join(ln), size, italic=True)
        x = W / 2 - lw / 2
        for w in ln:
            ww = text_width(ctx, w, size, italic=True)
            t0 = start + idx * per_word
            k = ramp(t, t0, 0.3)
            is_gold = w.strip(".,;:'’“”\"").lower() in gold
            if glow_words and k > 0:
                glow(ctx, x + ww / 2, y0 + li * lh - size * 0.3, ww * 0.9, C["gold"], 0.35 * (1 - ramp(t, t0 + 0.3, 1.2)))
            text(ctx, w, x + ww / 2, y0 + li * lh + (1 - ease_out(k)) * 16, size,
                 C["gold"] if is_gold else C["ink"], italic=True, alpha=k)
            x += ww + space
            idx += 1
    t_ref = start + idx * per_word + 0.2
    label(ctx, ref, W / 2, py + ph - 62, 26, alpha=ramp(t, t_ref, 0.4), grow=ease_out(ramp(t, t_ref + 0.1, 0.6)))
    for dx, dy in ((40, 40), (pw - 40, 40), (40, ph - 40), (pw - 40, ph - 40)):
        diamond(ctx, px + dx, py + dy, 7, C["gold"], pa)
    return start + idx * per_word
