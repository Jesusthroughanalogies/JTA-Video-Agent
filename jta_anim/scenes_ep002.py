"""Ep 2 animation scenes (Why Does God Allow Suffering?), one per [ANIM] and [TEXT] shot in
episodes/ep002/shots.py. Same framework, theme, cast and environment as Ep 1; new props for
this episode's three pictures: the puppet, the tapestry and the king's crown.

Preview:  python -m jta_anim.scenes_ep002 OUT_DIR [shot id ...]
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import cairo

from . import cast
from . import props as P
from . import scenes_ep001 as E1
from .core import (cached, clamp, diamond, ease_in_out, ease_out, label, lerp, outline_fill, pop, ramp, rgb,
                   rounded_rect, text)
from .scenes_ep001 import Scene, word_label
from .theme import C, H, W

REG: dict[str, Scene] = {}


def scene(*ids: str, base: str = "day", captions: bool = True, gold: tuple = ()):
    def deco(fn):
        for i in ids:
            REG[i] = Scene(fn, base, captions, gold)
        return fn
    return deco


def render_shot(shot_id, seconds, out, **kw):
    """Ep 1's renderer, pointed at this episode's scene registry."""
    saved = E1.REG
    E1.REG = REG
    try:
        return E1.render_shot(shot_id, seconds, out, **kw)
    finally:
        E1.REG = saved


WOOD, WOOD_D = C["bronze_face"], C["bronze"]

# ================================================================ props


def puppet(ctx, x, fy, s, *, bow=0.0, arm=0.0, smile=1.0, strings=1.0, snap=0.0, glow_arm=0.0, a=1.0,
           scroll=0.0):
    """A carved wooden marionette, feet at (x, fy). bow 0..1 bends at the hips; arm 0..1 raises its right
    arm; snap 0..1 breaks the strings (they recoil upward); scroll 0..1 shows a small scroll in its hand."""
    u = s / 100
    bar_y = fy - 330 * u
    ctx.save()
    ctx.push_group()
    hip = (x, fy - 70 * u)
    ang = bow * 0.55
    # positions after the bow (rotate the upper body about the hip)

    def up(px, py):
        dx, dy = px - hip[0], py - hip[1]
        return hip[0] + dx * math.cos(ang) - dy * math.sin(ang), hip[1] + dx * math.sin(ang) + dy * math.cos(ang)
    head = up(x, fy - 190 * u)
    hand_l = up(x - 52 * u, fy - 95 * u)
    hand_r = up(lerp(x + 52 * u, x + 70 * u, arm), lerp(fy - 95 * u, fy - 200 * u, arm))
    sh_l, sh_r = up(x - 30 * u, fy - 150 * u), up(x + 30 * u, fy - 150 * u)
    # strings
    if strings > 0:
        tips = [(head, 0), (hand_l, -1), (hand_r, 1), ((x - 14 * u, fy - 40 * u), -0.5), ((x + 14 * u, fy - 40 * u), 0.5)]
        for (px, py), side in tips:
            top = (x + side * 80 * u, bar_y)
            k = 1 - ease_out(snap)
            ex, ey = lerp(top[0], px, k), lerp(top[1], py, k)
            is_arm = side == 1
            ctx.move_to(*top)
            ctx.line_to(ex, ey)
            if is_arm and glow_arm:
                rgb(ctx, C["gold"], strings)
                ctx.set_line_width(5)
            else:
                rgb(ctx, C["ink"], 0.75 * strings)
                ctx.set_line_width(2)
            ctx.stroke()
        rounded_rect(ctx, x - 100 * u, bar_y - 10 * u, 200 * u, 20 * u, 6 * u)   # control bar
        outline_fill(ctx, WOOD_D, width=3, a=strings)
    # legs
    for dx in (-14, 14):
        rounded_rect(ctx, x + dx * u - 9 * u, fy - 72 * u, 18 * u, 72 * u, 8 * u)
        outline_fill(ctx, WOOD, width=3)
    # arms
    for (sx, sy), (hx, hy) in ((sh_l, hand_l), (sh_r, hand_r)):
        ctx.move_to(sx, sy)
        ctx.line_to(hx, hy)
        rgb(ctx, C["ink"])
        ctx.set_line_width(20 * u + 6)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.stroke()
        ctx.move_to(sx, sy)
        ctx.line_to(hx, hy)
        rgb(ctx, WOOD)
        ctx.set_line_width(20 * u)
        ctx.stroke()
    # body (rotated)
    ctx.save()
    ctx.translate(*hip)
    ctx.rotate(ang)
    rounded_rect(ctx, -32 * u, -88 * u, 64 * u, 92 * u, 14 * u)
    outline_fill(ctx, C["terracotta"], width=3.5)
    ctx.rectangle(-32 * u, -20 * u, 64 * u, 8 * u)
    rgb(ctx, C["gold"])
    ctx.fill()
    ctx.restore()
    # head
    ctx.arc(head[0], head[1], 32 * u, 0, 2 * math.pi)
    outline_fill(ctx, WOOD, width=3.5)
    for ex in (-11, 11):
        ctx.arc(head[0] + ex * u, head[1] - 4 * u, 3.5 * u, 0, 2 * math.pi)
        rgb(ctx, C["ink"])
        ctx.fill()
    ctx.new_path()
    if smile > 0.5:
        ctx.arc(head[0], head[1] + 6 * u, 12 * u, 0.15 * math.pi, 0.85 * math.pi)
    else:
        ctx.move_to(head[0] - 9 * u, head[1] + 13 * u)
        ctx.line_to(head[0] + 9 * u, head[1] + 13 * u)
    rgb(ctx, C["ink"])
    ctx.set_line_width(3)
    ctx.stroke()
    if scroll > 0:
        hx, hy = hand_r
        ctx.save()
        ctx.translate(hx + 10 * u, hy - 50 * u)
        sc = ease_out(scroll)
        ctx.scale(sc, sc)
        rounded_rect(ctx, -110 * u, -30 * u, 220 * u, 60 * u, 10 * u)
        outline_fill(ctx, C["papyrus"], width=3)
        text(ctx, "I LOVE YOU", 0, 9 * u, 26 * u, C["ink"], spacing=3)
        ctx.restore()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()


THREADS = (C["terracotta"], C["gold"], C["indigo"], C["olive"], C["bronze"])


def weave_back(ctx, x, y, w, h, *, a=1.0, seed=3, tangle=1.0):
    """The back of a weaving: crossing threads, knots and loose ends."""
    rnd = random.Random(seed)
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    rgb(ctx, C["papyrus_dark"], a)
    ctx.paint()
    for _ in range(70):
        col = rnd.choice(THREADS)
        x0, y0 = x + rnd.random() * w, y + rnd.random() * h
        x1, y1 = x0 + rnd.uniform(-w * 0.4, w * 0.4) * tangle, y0 + rnd.uniform(-h * 0.4, h * 0.4) * tangle
        ctx.move_to(x0, y0)
        ctx.curve_to(x0 + rnd.uniform(-80, 80), y0 + rnd.uniform(-80, 80), x1 + rnd.uniform(-80, 80),
                     y1 + rnd.uniform(-80, 80), x1, y1)
        rgb(ctx, col, 0.9 * a)
        ctx.set_line_width(rnd.uniform(4, 9))
        ctx.stroke()
        ctx.arc(x1, y1, rnd.uniform(5, 9), 0, 2 * math.pi)      # knot
        rgb(ctx, col, a)
        ctx.fill()
    ctx.restore()
    rounded_rect(ctx, x, y, w, h, 4)
    rgb(ctx, C["ink"], a)
    ctx.set_line_width(4)
    ctx.stroke()


def weave_front(ctx, x, y, w, h, *, a=1.0):
    """The front of the weaving: the sunrise picture, with a fine woven texture over it."""
    ctx.save()
    ctx.push_group()
    P.sunrise(ctx, x, y, w, h)
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    rgb(ctx, C["ink"], 0.08)
    ctx.set_line_width(1.2)
    step = max(6.0, w / 90)
    xx = x
    while xx < x + w:
        ctx.move_to(xx, y)
        ctx.line_to(xx, y + h)
        xx += step
    ctx.stroke()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()
    rounded_rect(ctx, x, y, w, h, 4)
    rgb(ctx, C["ink"], a)
    ctx.set_line_width(4)
    ctx.stroke()


def crown(ctx, cx, cy, s, a=1.0):
    u = s / 100
    ctx.move_to(cx - 60 * u, cy + 30 * u)
    ctx.line_to(cx - 60 * u, cy - 25 * u)
    ctx.line_to(cx - 30 * u, cy + 5 * u)
    ctx.line_to(cx, cy - 40 * u)
    ctx.line_to(cx + 30 * u, cy + 5 * u)
    ctx.line_to(cx + 60 * u, cy - 25 * u)
    ctx.line_to(cx + 60 * u, cy + 30 * u)
    ctx.close_path()
    outline_fill(ctx, C["gold"], width=4, a=a)
    for dx in (-60, 0, 60):
        ctx.arc(cx + dx * u, cy + (-25 if dx else -40) * u - 8 * u, 8 * u, 0, 2 * math.pi)
        outline_fill(ctx, C["terracotta"], width=3, a=a)
    ctx.rectangle(cx - 60 * u, cy + 14 * u, 120 * u, 8 * u)
    rgb(ctx, C["bronze"], a)
    ctx.fill()


def scroll(ctx, cx, cy, w, h, open_=1.0, a=1.0, lines=True):
    """A papyrus scroll unrolling sideways from its centre."""
    ww = max(20.0, w * ease_out(open_))
    rounded_rect(ctx, cx - ww / 2, cy - h / 2, ww, h, 6)
    outline_fill(ctx, C["papyrus"], a=a)
    if lines and open_ > 0.3:
        rgb(ctx, C["ink"], 0.25 * a * ramp(open_, 0.3, 0.7))
        for i in range(6):
            yy = cy - h / 2 + 60 + i * (h - 120) / 5
            ctx.rectangle(cx - ww / 2 + 50, yy, max(0, ww - 100) * (0.75 + 0.25 * ((i * 37) % 5) / 4), 5)
            ctx.fill()
    for side in (-1, 1):
        rounded_rect(ctx, cx + side * ww / 2 - 18, cy - h / 2 - 20, 36, h + 40, 14)
        outline_fill(ctx, C["bronze"], a=a)


def icon(ctx, k, cx, cy, s=1.0, a=1.0):
    if a <= 0:
        return
    if k == 0:
        puppet(ctx, cx, cy + 105 * s, 62 * s, a=a)
    elif k == 1:
        weave_front(ctx, cx - 110 * s, cy - 75 * s, 220 * s, 150 * s, a=a)
    else:
        crown(ctx, cx, cy, 150 * s, a=a)


NAMES = ("The puppet", "The tapestry", "The king")


def triptych(ctx, states):
    """Ep 2's three frames: the puppet, the tapestry, the king."""
    for k, st in enumerate(states):
        if st.get("alpha", 1) <= 0:
            continue
        x, y, sc = st.get("x", P.FRAME_SLOTS[k]), st.get("y", P.FRAME_Y), st.get("scale", 1.0)
        a = st.get("alpha", 1.0)
        P.picture_frame(ctx, x, y, P.FRAME_W, P.FRAME_H, lit=st.get("lit", 0.0), alpha=a, scale=sc)
        icon(ctx, k, x, y, sc, a * st.get("fill", 0.0))
        if st.get("title", 0) > 0:
            text(ctx, NAMES[k].upper(), x, y + (P.FRAME_H / 2 + 75) * sc, 26 * sc, C["ink"], spacing=6,
                 alpha=a * st["title"])
        if st.get("tick", 0) > 0:
            ctx.arc(x + P.FRAME_W / 2 * sc, y - P.FRAME_H / 2 * sc, 34 * sc, 0, 2 * math.pi)
            outline_fill(ctx, C["papyrus"], a=a)
            P.tick(ctx, x + P.FRAME_W / 2 * sc, y - P.FRAME_H / 2 * sc, 34 * sc, st["tick"])


def frame_transition(ctx, t, s, done, key):
    t_tick, t_move, t_in = s.at(0.15), s.at(0.45), s.wt(key, 0.6)
    sts = []
    for k in range(3):
        st = {"fill": 1.0 if k <= done else 0.0, "title": 1.0 if k < done else 0.0}
        if k < done:
            st.update(lit=0.25, tick=1.0)
        elif k == done:
            m = ease_in_out(ramp(t, t_move, 0.9))
            st.update(x=lerp(W / 2, P.FRAME_SLOTS[k], m), scale=lerp(1.5, 1.0, m), lit=ramp(t, t_tick, 0.3),
                      tick=ramp(t, t_tick + 0.2, 0.4), title=m)
        elif k == done + 1:
            u = ease_out(ramp(t, t_in, 0.7))
            st.update(x=lerp(W + 300, P.FRAME_SLOTS[k], u), fill=u, title=ramp(t, t_in + 0.5, 0.4),
                      alpha=1.0 if u > 0 else 0)
        else:
            st.update(alpha=0.0)
        sts.append(st)
    triptych(ctx, sts)


def earth(ctx, cx, cy, r, t, *, plates=0.0, crack=0.0, gold=0.0, carbon=0.0, a=1.0):
    """Cut-away of the earth: core, mantle, a crust of plates that slide, a breathing volcano,
    carbon arrows looping sea -> rock -> sky, an optional hairline crack that fills with gold."""
    ctx.save()
    ctx.push_group()
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    outline_fill(ctx, C["indigo"])
    ctx.arc(cx, cy, r * 0.86, 0, 2 * math.pi)
    outline_fill(ctx, C["terracotta"], width=3)
    ctx.arc(cx, cy, r * 0.42, 0, 2 * math.pi)
    outline_fill(ctx, C["sun"], width=3)
    # crust plates on the upper rim (land), sliding apart and together
    for i, (a0, a1) in enumerate(((-2.6, -1.9), (-1.85, -1.25), (-1.2, -0.5))):
        d = 0.025 * math.sin(t * 1.6 + i * 2) * plates
        ctx.arc(cx, cy, r * 1.02, a0 + d, a1 + d)
        ctx.arc_negative(cx, cy, r * 0.9, a1 + d, a0 + d)
        ctx.close_path()
        outline_fill(ctx, C["dune_mid"], width=3)
    # volcano on the middle plate
    vx, vy = cx + r * 1.0 * math.cos(-1.55), cy + r * 1.0 * math.sin(-1.55)
    ctx.move_to(vx - 50, vy + 8)
    ctx.line_to(vx - 12, vy - 46)
    ctx.line_to(vx + 12, vy - 46)
    ctx.line_to(vx + 50, vy + 8)
    ctx.close_path()
    outline_fill(ctx, C["stone_shade"], width=3)
    puff = 0.5 + 0.5 * math.sin(t * 2)
    for j in range(3):
        ctx.arc(vx + j * 14 - 10, vy - 70 - j * 26 - puff * 10, 16 + j * 6, 0, 2 * math.pi)
        rgb(ctx, C["seeker_robe"], 0.55 * plates)
        ctx.fill()
    if crack > 0:
        pts = [(cx - r * 0.95, cy - r * 0.1), (cx - r * 0.5, cy + r * 0.05), (cx - r * 0.2, cy - r * 0.08),
               (cx + r * 0.2, cy + r * 0.1), (cx + r * 0.55, cy - r * 0.02), (cx + r * 0.95, cy + r * 0.12)]
        n = max(2, int(len(pts) * crack + 0.999))
        ctx.move_to(*pts[0])
        for p in pts[1:n]:
            ctx.line_to(*p)
        rgb(ctx, C["gold"] if gold else C["ink"])
        ctx.set_line_width(4 + 10 * gold)
        ctx.stroke()
        if gold:
            for p in pts:
                P.glow(ctx, p[0], p[1], 90, C["sun"], 0.5 * gold)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()
    if carbon > 0:   # looping arrows: sea -> rock -> sky -> sea
        loop = [(cx + r * 1.25, cy + r * 0.4), (cx + r * 0.2, cy + r * 1.25), (cx - r * 1.25, cy + r * 0.3),
                (cx - r * 0.9, cy - r * 1.2), (cx + r * 0.9, cy - r * 1.2)]
        lbl = ("SEA", "ROCK", "", "SKY", "")
        for i in range(len(loop)):
            p0, p1 = loop[i], loop[(i + 1) % len(loop)]
            k = clamp(carbon * len(loop) - i)
            if k > 0:
                P.arrow(ctx, p0[0], p0[1], p1[0], p1[1], col=C["olive"], width=5, a=a, p=k)
            if lbl[i] and k > 0:
                text(ctx, lbl[i], p0[0], p0[1] - 20, 26, C["olive"], spacing=5, alpha=k * a)


# ================================================================ HOOK

def _doorway(ctx, x, fy, h, a=1.0, glow=1.0):
    P.glow(ctx, x, fy - h / 2, h * 1.1, C["sun"], 0.45 * glow * a)
    rounded_rect(ctx, x - h * 0.28, fy - h, h * 0.56, h, 10)
    outline_fill(ctx, C["sun"], a=a)
    for side in (-1, 1):   # temple door posts
        ctx.rectangle(x + side * h * 0.28 - (30 if side > 0 else 0), fy - h - 20, 30, h + 20)
        outline_fill(ctx, C["column"], a=a)
    ctx.rectangle(x - h * 0.28 - 40, fy - h - 50, h * 0.56 + 80, 40)
    outline_fill(ctx, C["stone_lit"], a=a)


@scene("H-03", base="night", gold=("walk", "away", "never"))
def h03(ctx, t, s):
    _doorway(ctx, 620, 760, 360, glow=1 - 0.4 * ramp(t, 1, s.dur))
    u = ease_in_out(ramp(t, 0.3, s.dur - 0.3))
    x = lerp(720, 1500, u)
    h = lerp(260, 200, u)
    cast.seeker(ctx, x, 760 + 10 * u, h, view="back", step=math.sin(t * 6), alpha=1 - 0.5 * u)


@scene("H-04", gold=("why?", "how", "long?"))
def h04(ctx, t, s):
    k = ease_out(ramp(t, 0.1, 0.9))
    scroll(ctx, W / 2, 470, 1100, 460, open_=k, lines=False)
    for wd, key, y, f in (("WHY?", "why", 430, 0.45), ("HOW LONG?", "how", 560, 0.75)):
        t0 = s.wt(key, f)
        word_label(ctx, wd, W / 2, y, t, t0, size=96, col=C["ink"])


@scene("H-05", gold=("three", "pictures", "objection"))
def h05(ctx, t, s):
    sts = []
    for k in range(3):
        u = ease_out(ramp(t, 0.2 + k * 0.25, 0.7))
        sts.append({"x": lerp(W + 300, P.FRAME_SLOTS[k], u), "alpha": 1.0 if u > 0 else 0.0})
    triptych(ctx, sts)


@scene("H-06", gold=("puppet.", "tapestry.", "king."))
def h06(ctx, t, s):
    keys = (("puppet", 0.25), ("tapestry", 0.5), ("king", 0.8))
    sts = []
    for k, (w, f) in enumerate(keys):
        t0 = s.wt(w, f)
        sts.append({"fill": ease_out(ramp(t, t0, 0.4)), "title": ramp(t, t0 + 0.2, 0.4),
                    "lit": 0.6 * math.exp(-max(t - t0, 0) * 2) * (t >= t0)})
    triptych(ctx, sts)


@scene("H-07", base="night", captions=False)
def h07(ctx, t, s):
    pa = ease_out(ramp(t, 0.0, 0.4))
    rounded_rect(ctx, 260, 330, 1400, 460, 24)
    rgb(ctx, C["night_bg"], 0.85 * pa)
    ctx.fill()
    P.glow(ctx, W / 2, 480, 700, C["gold"], 0.25 * ramp(t, 0.1, 0.8))
    text(ctx, "WHY DOES GOD", W / 2, 470, 110, C["night_text"], spacing=14, alpha=ramp(t, 0.1, 0.4),
         scale=pop(t, 0.1, 0.45), shadow=True)
    text(ctx, "ALLOW SUFFERING?", W / 2, 610, 110, C["gold"], spacing=14, alpha=ramp(t, 0.45, 0.4),
         scale=pop(t, 0.45, 0.45), shadow=True)
    label(ctx, "Jesus Through Analogies · Episode 2", W / 2, 730, 30, col=C["night_text"], alpha=ramp(t, 0.9, 0.5),
          grow=ease_out(ramp(t, 1.0, 0.6)))


# ================================================================ PART 1: the puppet

PX, PFY, PS = W / 2, 820, 170


@scene("P1-02", gold=("smiles.", "bows.", "never"))
def p102(ctx, t, s):
    tb = s.wt("bows", 0.45)
    bow = math.sin(math.pi * ramp(t, tb, 1.0)) * 0.9
    ta = s.wt("smiles", 0.25)
    arm = math.sin(math.pi * ramp(t, ta, 1.0)) * 0.8
    puppet(ctx, PX, PFY, PS, bow=bow, arm=arm)


@scene("P1-03", gold=("can't", "love", "doesn't"))
def p103(ctx, t, s):
    t_s = s.wt("i", 0.45)
    puppet(ctx, PX, PFY, PS, arm=ease_out(ramp(t, t_s - 0.5, 0.6)), scroll=ramp(t, t_s - 0.2, 0.5),
           glow_arm=ramp(t, s.wt("pulled", 0.7), 0.3))


@scene("P1-04", gold=("chosen.", "free", "opposite."))
def p104(ctx, t, s):
    t_snap = s.wt("chosen", 0.3)
    sn = ramp(t, t_snap, 0.5)
    # two paths open behind: one lit, one dark
    pa = ease_out(ramp(t, s.wt("free", 0.55), 0.8))
    for side, col in ((-1, C["sun"]), (1, C["ink"])):
        ctx.move_to(PX + side * 30, PFY)
        ctx.curve_to(PX + side * 200, PFY - 80, PX + side * 420, PFY - 150, PX + side * 700, PFY - 200)
        rgb(ctx, col, 0.6 * pa)
        ctx.set_line_width(lerp(40, 10, 0.5))
        ctx.stroke()
    if pa:
        P.glow(ctx, PX - 700, PFY - 200, 200, C["sun"], 0.5 * pa)
    # the puppet's strings snap and it becomes a person standing on its own
    turn = ease_in_out(ramp(t, t_snap + 0.6, 0.6))
    puppet(ctx, PX, PFY, PS, snap=sn, strings=1 - ramp(t, t_snap + 0.3, 0.4), a=1 - turn)
    if turn > 0:
        cast.seeker(ctx, PX, PFY, 300, view="front", alpha=turn)


@scene("P1-07", gold=("sin.", "missing", "mark:"))
def p107(ctx, t, s):
    ax, tx_, fy = 520, 1440, 800
    t_fire = s.wt("missing", 0.4)
    draw = ease_in_out(ramp(t, t_fire - 1.0, 0.9)) * (t < t_fire)
    cast.archer(ctx, ax, fy, 280, robe="olive", draw=draw)
    # target: wooden board on a stand
    ctx.rectangle(tx_ - 10, fy - 200, 20, 200)
    outline_fill(ctx, WOOD_D)
    for r, col in ((130, C["papyrus"]), (95, C["terracotta"]), (60, C["papyrus"]), (28, C["gold"])):
        ctx.arc(tx_, fy - 330, r, 0, 2 * math.pi)
        outline_fill(ctx, col, width=4)
    if t >= t_fire:   # the arrow flies and misses high and wide
        u = ease_out(ramp(t, t_fire, 0.7))
        x = lerp(ax + 80, tx_ + 260, u)
        y = lerp(fy - 170, fy - 520, u) - 60 * math.sin(u * math.pi)
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(-0.25)
        ctx.move_to(-70, 0)
        ctx.line_to(30, 0)
        rgb(ctx, C["ink"])
        ctx.set_line_width(5)
        ctx.stroke()
        ctx.move_to(30, -10)
        ctx.line_to(50, 0)
        ctx.line_to(30, 10)
        ctx.close_path()
        outline_fill(ctx, C["bronze"], width=2)
        ctx.restore()
    k = ramp(t, t_fire + 0.6, 0.4)
    if k:
        rounded_rect(ctx, W / 2 - 360, 150, 720, 90, 14)
        outline_fill(ctx, C["papyrus"], a=k)
        text(ctx, "SIN = MISSING THE MARK", W / 2, 212, 44, C["terracotta"], spacing=6, alpha=k, scale=pop(t, t_fire + 0.6))


@scene("P1-10", "P3-13", gold=("hardest", "pretend", "end"))
def qmark(ctx, t, s):
    k = ramp(t, 0.1, 0.6)
    y = lerp(-100, 560, ease_out(k)) + 8 * math.sin(t * 1.5) * k
    P.question_mark(ctx, W / 2, y, 420, a=k, rot=0.06 * math.sin(t))


@scene("P1-13", gold=("dials", "same", "plates", "life."))
def p113(ctx, t, s):
    k = ease_out(ramp(t, 0.1, 0.8))
    earth(ctx, W / 2, 520, 260 * k + 1, t, plates=ramp(t, s.wt("plates", 0.35), 0.6),
          carbon=ramp(t, s.wt("recycle", 0.6), 2.5), a=k)
    label(ctx, "The same rules", W / 2, 140, 34, alpha=ramp(t, s.wt("same", 0.3), 0.4),
          grow=ease_out(ramp(t, s.wt("same", 0.3) + 0.1, 0.6)))


@scene("P1-14", gold=("broken,",))
def p114(ctx, t, s):
    earth(ctx, W / 2, 520, 260, t, plates=1.0, crack=ease_in_out(ramp(t, s.wt("broken", 0.5), 0.8)))


@scene("P1-15", captions=False)
def p115(ctx, t, s):
    P.verse_card(ctx, t, "We know that the whole creation has been groaning as in the pains of childbirth right up "
                 "to the present time.", "Romans 8:22 · NIV", gold=("groaning", "childbirth"),
                 per_word=min(0.2, s.dur * 0.6 / 21))


@scene("P1-16", gold=("labour.", "waiting", "born."))
def p116(ctx, t, s):
    earth(ctx, W / 2, 520, 260, t, plates=1.0, crack=1.0, gold=ease_in_out(ramp(t, s.wt("waiting", 0.5), 1.0)))


@scene("P1-17", gold=("freedom,", "broken.", "second"))
def p117(ctx, t, s):
    frame_transition(ctx, t, s, 0, "second")


# ================================================================ PART 2: the tapestry

TX, TY, TW_, TH_ = W / 2 - 420, 200, 840, 560


@scene("P2-02", gold=("back.", "knots.", "loose"))
def p202(ctx, t, s):
    k = ease_out(ramp(t, 0.1, 0.6))
    weave_back(ctx, TX, TY + (1 - k) * 40, TW_, TH_, a=k, tangle=1.0)


@scene("P2-03", gold=("front.", "picture.", "every"))
def p203(ctx, t, s):
    t_f = s.wt("front", 0.3)
    u = ease_in_out(ramp(t, t_f - 0.2, 0.8))
    sx = abs(math.cos(u * math.pi))       # flip about the vertical axis
    ctx.save()
    ctx.translate(W / 2, 0)
    ctx.scale(max(sx, 0.01), 1)
    ctx.translate(-W / 2, 0)
    if u < 0.5:
        weave_back(ctx, TX, TY, TW_, TH_)
    else:
        weave_front(ctx, TX, TY, TW_, TH_)
    ctx.restore()
    if u >= 1:
        P.glow(ctx, W / 2, TY + TH_ / 2, 600, C["gold"], 0.2 * ramp(t, t_f + 0.6, 0.5))


@scene("P2-09", gold=("brothers", "terrified,"))
def p209(ctx, t, s):
    fy = 820
    # Joseph: an Egyptian official in a gold robe with a broad collar
    cast.crowd_figure(ctx, 1380, fy, 330, "gold")
    ctx.arc(1380, fy - 255, 34, 0.1 * math.pi, 0.9 * math.pi)
    rgb(ctx, C["indigo"])
    ctx.set_line_width(14)
    ctx.stroke()
    # his brothers kneel (shorter figures, bowed), dressed in dyed robes
    for i, (x, robe) in enumerate(((520, "terracotta"), (700, "olive"), (880, "indigo"), (1060, "bronze"))):
        k = ease_out(ramp(t, 0.2 + i * 0.12, 0.6))
        cast.crowd_figure(ctx, x, fy, lerp(300, 190, k), robe)


@scene("P2-10", captions=False)
def p210(ctx, t, s):
    P.verse_card(ctx, t, "You intended to harm me, but God intended it for good to accomplish what is now being done, "
                 "the saving of many lives.", "Genesis 50:20 · NIV", gold=("harm", "good", "saving"),
                 size=60, pw=1400, max_w=1180, per_word=min(0.18, s.dur * 0.6 / 24))


@scene("P2-11", gold=("same", "two", "sides"))
def p211(ctx, t, s):
    k = ease_out(ramp(t, 0.1, 0.6))
    weave_back(ctx, 160, 230, 760, 500, a=k)
    weave_front(ctx, 1000, 230, 760, 500, a=ease_out(ramp(t, s.wt("two", 0.4), 0.6)))
    text(ctx, "WHAT WE SEE", 540, 800, 30, C["ink"], spacing=6, alpha=k)
    text(ctx, "WHAT GOD SEES", 1380, 800, 30, C["gold"], spacing=6, alpha=ramp(t, s.wt("sides", 0.6), 0.4))


@scene("P2-12", gold=("cop-out.", "anything"))
def p212(ctx, t, s):
    cast.seeker(ctx, 760, 820, 340, view="front", shrug=ease_out(ramp(t, 0.3, 0.6)))
    t_s = s.wt("cop", 0.25)
    k = ramp(t, t_s, 0.2)
    if k:
        ctx.save()
        ctx.translate(1230, 470)
        ctx.rotate(-0.12)
        sc = lerp(1.8, 1.0, ease_out(k))
        ctx.scale(sc, sc)
        rounded_rect(ctx, -230, -70, 460, 140, 14)
        rgb(ctx, C["terracotta"], k)
        ctx.set_line_width(8)
        ctx.stroke()
        text(ctx, "COP-OUT?", 0, 26, 76, C["terracotta"], spacing=8, alpha=k)
        ctx.restore()


def _healing(ctx, t, z, fx, fy):
    """Father kneeling holding his daughter; a healer with a clay bowl tends her arm."""
    ctx.save()
    ctx.translate(fx, fy)
    ctx.scale(z, z)
    ctx.translate(-fx, -fy)
    base = 820
    cast.crowd_figure(ctx, 820, base, 250, "indigo")          # father (kneeling: shorter)
    cast.crowd_figure(ctx, 900, base, 150, "terracotta")      # daughter on his knee
    ctx.move_to(835, base - 150)                              # his arm around her
    ctx.curve_to(870, base - 100, 905, base - 70, 935, base - 75)
    rgb(ctx, C["skin"])
    ctx.set_line_width(16)
    ctx.stroke()
    cast.crowd_figure(ctx, 1140, base, 280, "olive")          # healer
    P.ellipse(ctx, 1050, base - 120, 46, 16)                  # clay bowl
    outline_fill(ctx, C["terracotta"], width=3)
    ctx.restore()


@scene("P2-14", gold=("father", "healer", "cut."))
def p214(ctx, t, s):
    _healing(ctx, t, 1.5, 980, 820)


@scene("P2-15", gold=("hurt.", "can't", "infection"))
def p215(ctx, t, s):
    z = lerp(3.2, 1.5, ease_in_out(ramp(t, s.wt("can't", 0.5) - 0.3, 1.4)))
    _healing(ctx, t, z, 960, 800)


@scene("P2-16", gold=("seeing", "reason", "no"))
def p216(ctx, t, s):
    word_label(ctx, "CAN'T SEE", W / 2, 360, t, s.at(0.1), size=100)
    word_label(ctx, "IS NOT THE SAME AS", W / 2, 500, t, s.wt("isn't", 0.4), size=46, col=C["gold"])
    word_label(ctx, "ISN'T THERE", W / 2, 650, t, s.wt("no", 0.6), size=100)


@scene("P2-17", gold=("worth", "lost", "sheer"))
def p217(ctx, t, s):
    n = int(clamp(t / max(s.dur - 0.6, 0.5)) * 14) + 1
    for i in range(n):
        y = 820 - i * 46
        k = ramp(t, i * (s.dur - 0.6) / 14, 0.25)
        yy = y - (1 - ease_out(k)) * 60
        rounded_rect(ctx, W / 2 - 170 + (i % 2) * 14, yy - 36, 340, 40, 18)
        outline_fill(ctx, C["papyrus"], a=k, width=3.5)
        for side in (-1, 1):
            rounded_rect(ctx, W / 2 + side * 170 - 12 + (i % 2) * 14, yy - 42, 24, 52, 10)
            outline_fill(ctx, C["bronze"], a=k, width=3)


@scene("P2-18", gold=("unfair.", "wrong", "better."))
def p218(ctx, t, s):
    t_u = s.wt("unfair", 0.35)
    k = ramp(t, t_u, 0.3)
    P.glow(ctx, W / 2, 560, 420, C["gold"], 0.4 * k)
    text(ctx, "UNFAIR", W / 2, 600, 140, C["terracotta"], spacing=16, alpha=k, scale=pop(t, t_u), shadow=True)
    t_b = s.wt("clue", 0.75)
    P.arrow(ctx, W / 2, 470, W / 2, 120, col=C["gold"], width=8, head=30, p=ease_out(ramp(t, t_b, 0.8)))


@scene("P2-19", gold=("weaver", "threads?", "third"))
def p219(ctx, t, s):
    frame_transition(ctx, t, s, 1, "third")


# ================================================================ PART 3: the king

@scene("P3-03", gold=("crown,", "gates,", "sick."))
def p303(ctx, t, s):
    fy = 820
    # throne
    rounded_rect(ctx, 380, fy - 330, 200, 330, 10)
    outline_fill(ctx, C["bronze"])
    rounded_rect(ctx, 360, fy - 160, 240, 50, 8)
    outline_fill(ctx, C["gold"])
    # city gate on the right
    rounded_rect(ctx, 1500, fy - 380, 260, 380, 120)
    outline_fill(ctx, C["stone_shade"])
    rounded_rect(ctx, 1560, fy - 300, 140, 300, 70)
    outline_fill(ctx, C["night_bg"])
    t_c = s.wt("crown", 0.2)
    cu = ease_in_out(ramp(t, t_c, 0.8))
    walk = ease_in_out(ramp(t, s.wt("walk", 0.45), max(1.0, s.dur - s.wt("walk", 0.45) - 0.2)))
    x = lerp(620, 1560, walk)
    cast.crowd_figure(ctx, x, fy, 300, "indigo")
    crown(ctx, lerp(x, 480, cu), lerp(fy - 330, fy - 200, cu), 90)


@scene("P3-07", captions=False)
def p307(ctx, t, s):
    P.verse_card(ctx, t, "Jesus wept.", "John 11:35 · NIV", gold=("wept.",), size=110, per_word=0.35)


@scene("P3-10", gold=("isaiah", "described"))
def p310(ctx, t, s):
    scroll(ctx, W / 2, 480, 1150, 500, open_=ramp(t, 0.1, 1.2))


@scene("P3-11", captions=False)
def p311(ctx, t, s):
    P.verse_card(ctx, t, "He was despised and rejected by mankind, a man of suffering, and familiar with pain.",
                 "Isaiah 53:3 · NIV", gold=("suffering,", "pain."), per_word=min(0.2, s.dur * 0.6 / 16))


@scene("P3-15", captions=False)
def p315(ctx, t, s):
    P.verse_card(ctx, t, "He will wipe every tear from their eyes. There will be no more death or mourning or crying "
                 "or pain.", "Revelation 21:4 · NIV", gold=("tear", "death"), per_word=min(0.2, s.dur * 0.6 / 22))


@scene("P3-16", captions=False)
def p316(ctx, t, s):
    P.verse_card(ctx, t, "In this world you will have trouble. But take heart! I have overcome the world.",
                 "John 16:33 · NIV", gold=("trouble.", "overcome"), per_word=min(0.2, s.dur * 0.6 / 16))


# ================================================================ PART 4

def _lit_one(ctx, t, s, which):
    sts = []
    for k in range(3):
        on = k <= which
        t0 = 0.2 if k == which else -1
        sts.append({"fill": 1.0, "title": 1.0, "lit": (ease_out(ramp(t, t0, 0.5)) if k == which else 0.35 if on else 0.0),
                    "scale": 1 + 0.08 * math.exp(-max(t - t0, 0) * 3) * (k == which)})
    triptych(ctx, sts)


@scene("P4-01", gold=("puppet:", "freedom,"))
def p401(ctx, t, s):
    _lit_one(ctx, t, s, 0)


@scene("P4-02", gold=("tapestry:", "back,"))
def p402(ctx, t, s):
    _lit_one(ctx, t, s, 1)


@scene("P4-03", gold=("king:", "walked", "end"))
def p403(ctx, t, s):
    _lit_one(ctx, t, s, 2)


@scene("P4-06", gold=("feel.", "afraid"))
def p406(ctx, t, s):
    cast.seeker(ctx, 860, 820, 320, view="front", look_up=0.0)
    k = ease_out(ramp(t, 0.4, 1.5))
    gx, gy = lerp(1500, 1060, k), lerp(200, 600, k)
    P.glow(ctx, gx, gy, 160 + 80 * k, C["sun"], 0.55)
    ctx.arc(gx, gy, 18, 0, 2 * math.pi)
    rgb(ctx, C["papyrus"])
    ctx.fill()


# ================================================================ OUTRO

@scene("O-01", gold=("subscribe.", "every", "week"))
def o01(ctx, t, s):
    triptych(ctx, [{"fill": 1.0, "lit": 0.3, "scale": 0.7, "y": 300, "x": 960 + (k - 1) * 300} for k in range(3)])
    pa = ease_out(ramp(t, 0.2, 0.5))
    rounded_rect(ctx, 610, 520, 700, 190, 16)
    outline_fill(ctx, C["papyrus"], a=pa)
    t_s = s.wt("subscribe", 0.25)
    k = ramp(t, t_s, 0.25)
    if k > 0:
        sc = lerp(1.8, 1.0, ease_out(k))
        ctx.save()
        ctx.translate(1180, 615)
        ctx.scale(sc, sc)
        ctx.arc(0, 0, 58, 0, 2 * math.pi)
        outline_fill(ctx, C["terracotta"], a=k)
        text(ctx, "JTA", 0, 12, 30, C["papyrus"], alpha=k)
        ctx.restore()
    text(ctx, "SUBSCRIBE", 860, 632, 64, C["ink"], spacing=10, alpha=ramp(t, t_s + 0.15, 0.3), scale=pop(t, t_s + 0.15))
    text(ctx, "A new picture every week", 860, 685, 30, C["bronze"], italic=True,
         alpha=ramp(t, s.wt("every", 0.6), 0.4))


@scene("O-02", gold=("send", "hurting"))
def o02(ctx, t, s):
    E1.o02(ctx, t, s)


@scene("O-03", gold=("bible.", "changed", "checked."))
def o03(ctx, t, s):
    for i in range(7):
        k = ramp(t, 0.2 + i * 0.25, 0.4)
        x = 360 + i * 200
        scroll(ctx, x, 470 + (1 - ease_out(k)) * 60, 120, 300, open_=0.35, a=k, lines=False)
    t_n = s.wt("is", 0.6)
    k = ramp(t, t_n, 0.4)
    rounded_rect(ctx, W / 2 - 430, 690, 860, 110, 16)
    outline_fill(ctx, C["papyrus"], a=k)
    text(ctx, "NEXT: IS THE BIBLE RELIABLE?", W / 2, 762, 46, C["ink"], spacing=6, alpha=k, scale=pop(t, t_n))


# ---------------------------------------------------------------- preview

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "anim_out_ep002")
    ids = sys.argv[2:] or list(REG)
    for i in ids:
        render_shot(i, 4.0, out / f"{i}.png", line="", still_at=3.0)
        print("wrote", i)
