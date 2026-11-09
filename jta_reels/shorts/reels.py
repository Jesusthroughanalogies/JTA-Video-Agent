"""Four new JTA Shorts (9 Nov 2026). Brand-new scripts and analogies, nothing remixed.

Theology: non-denominational, Jesus-centred. Every quote is KJV, word for word.
  N1 Holy Spirit: a kite only flies when the wind takes it          John 3:8
  N2 Sin: a stain that spreads when you scrub it                   Isaiah 1:18
  N3 The cross: a growing debt, then "paid in full" (tetelestai)    John 19:30
  N4 Jesus the way: a canyon no one can jump, then a bridge        John 14:6
"""
from __future__ import annotations

import math
import random

import cairo

from .engine import (C, H, W, Beat, Reel, clamp, ease, ease_out, glow, grass, greek_card, hand_pos, hill,
                     hill_y, hx, label, lerp, person, ramp, rays, rgb, sky, stars, sun, tag, text)


def seg(t, a, b):
    return ease(ramp(t, a, max(b - a, 1e-3)))


def layer(ctx, alpha, fn):
    if alpha <= 0:
        return
    ctx.push_group()
    fn()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(alpha)


# =================================================================================== N1 kite
NEAR = dict(base=1380, amp=34, freq=0.55, phase=0.6)


def kite_shape(ctx, x, y, s, rot, t, wind):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    # tail, streaming downwind
    ctx.move_to(0, s * 0.62)
    pts = []
    for i in range(1, 9):
        u = i / 8
        px = -u * s * 1.6 * (0.4 + wind) + math.sin(t * 6 + u * 5) * 10 * (0.3 + wind)
        py = s * 0.62 + u * s * 1.4 * (1.2 - wind * 0.5)
        pts.append((px, py))
        ctx.line_to(px, py)
    rgb(ctx, C["sil"])
    ctx.set_line_width(2.5)
    ctx.stroke()
    for px, py in pts[1::2]:
        ctx.move_to(px - 9, py - 6)
        ctx.line_to(px + 9, py + 6)
        ctx.line_to(px + 9, py - 6)
        ctx.line_to(px - 9, py + 6)
        ctx.close_path()
        rgb(ctx, hx("#C7653F"))
        ctx.fill()
    # sail
    ctx.move_to(0, -s * 0.62)
    ctx.line_to(s * 0.42, -s * 0.1)
    ctx.line_to(0, s * 0.62)
    ctx.line_to(-s * 0.42, -s * 0.1)
    ctx.close_path()
    rgb(ctx, hx("#D9774A"))
    ctx.fill_preserve()
    rgb(ctx, C["sil"])
    ctx.set_line_width(3)
    ctx.stroke()
    ctx.move_to(0, -s * 0.62)
    ctx.line_to(0, s * 0.62)
    ctx.move_to(-s * 0.42, -s * 0.1)
    ctx.line_to(s * 0.42, -s * 0.1)
    ctx.set_line_width(2)
    ctx.stroke()
    ctx.restore()


def wind_streaks(ctx, t, strength):
    if strength <= 0:
        return
    rnd = random.Random(5)
    for i in range(14):
        y = 700 + rnd.random() * 700
        speed = 380 + rnd.random() * 260
        length = 180 + rnd.random() * 220
        x = (t * speed + rnd.random() * 2000) % (W + 800) - 400
        a = strength * (0.25 + 0.35 * rnd.random())
        ctx.move_to(x, y)
        for k in range(1, 13):
            u = k / 12
            ctx.line_to(x + u * length, y + math.sin(u * math.pi * 2 + t * 2 + i) * 10)
        g = cairo.LinearGradient(x, 0, x + length, 0)
        for p, al in ((0, 0), (0.5, a), (1, 0)):
            g.add_color_stop_rgba(p, *C["gold_soft"], al)
        ctx.set_source(g)
        ctx.set_line_width(2.4)
        ctx.stroke()


def draw_kite(r: Reel, ctx, t):
    B, BE = r.B, r.BE
    lift = seg(t, B("b10"), BE("b10"))
    rise = seg(t, B("b11"), BE("b13"))
    dim = seg(t, B("b4"), BE("b4")) * (1 - seg(t, B("b6"), BE("b6")))
    sky(ctx, "dusk", "dawn", 0.55 * rise)
    stars(ctx, t, 0.5 * (1 - lift))
    sy = lerp(1210, 1120, rise)
    rays(ctx, 760, sy, seg(t, B("b12"), BE("b12")) * 1.0, rot=t * 0.03)
    sun(ctx, 760, sy, 46, 0.9 + 0.1 * rise)
    hill(ctx, 1290, 26, 1.3, 2.0, "#5B3E5F")
    hill(ctx, 1360, 30, 0.9, 0.3, "#2E2140")
    hill(ctx, **NEAR, col="#120E1C")
    wind = seg(t, B("b7"), BE("b7")) * 0.6 + seg(t, B("b9"), BE("b9")) * 0.4
    grass(ctx, **NEAR, col="#120E1C", sway=0.15 + 0.6 * wind)
    wind_streaks(ctx, t, wind * (1 - 0.5 * rise))

    # figure: where they are and what they're doing
    if t < B("b2"):
        fx, run = 420, 0.0
    elif t < BE("b3"):
        fx, run = lerp(380, 720, seg(t, B("b2"), BE("b3"))), 1.0 - seg(t, B("b3") + 0.6, BE("b3"))
    elif t < B("b5"):
        fx, run = 720, 0.0
    elif t < BE("b5"):
        fx, run = lerp(720, 430, seg(t, B("b5"), BE("b5"))), 1.0
    else:
        fx, run = 430, 0.0
    fy = hill_y(fx, **NEAR) + 4
    step = math.sin(t * 16) * run
    slump = seg(t, B("b4"), B("b4") + 0.6) * (1 - seg(t, B("b5"), B("b5") + 0.3))
    arm_r = lerp(0.5, 2.3, lift) if t > B("b6") else (0.9 + 0.4 * math.sin(t * 16) * run)
    person(ctx, fx, fy, 300, step=step, lean=0.35 * run + 0.25 * slump, arm_l=-0.3 - 0.4 * run * math.sin(t * 16),
           arm_r=arm_r, look_up=lift, rim=rise)
    hx_, hy_ = hand_pos(fx, fy, 300, arm_r, 1, 0.35 * run + 0.25 * slump)

    # kite
    ground = lambda x: hill_y(x, **NEAR) - 10
    if t < B("b2") or (B("b4") <= t < B("b5")) or (BE("b5") <= t < B("b7")):
        kx = fx - 210 if t < B("b2") or t >= BE("b5") else fx - 220
        ky, rot, wind_k, sag = ground(kx), 1.25, 0.0, 1.0
    elif t < B("b3"):
        kx = fx - 170
        ky = ground(kx) - 30 - 40 * abs(math.sin(t * 7))
        rot, wind_k, sag = 0.9 + 0.2 * math.sin(t * 7), 0.1, 0.6
    elif t < BE("b3"):
        u = ramp(t, B("b3"), BE("b3") - B("b3"))
        kx = fx - 200 + 40 * u
        hgt = 300 * math.sin(clamp(u * 1.25) * math.pi) if u < 0.8 else 0
        ky = ground(kx) - hgt
        rot, wind_k, sag = 0.3 + 1.0 * clamp((u - 0.45) * 2), 0.2, 0.5
    elif t < BE("b5"):
        u = ramp(t, B("b5"), BE("b5") - B("b5"))
        kx = fx + 170
        ky = ground(kx) - 120 * math.sin(clamp(u * 1.6) * math.pi) * (u < 0.62)
        rot, wind_k, sag = 0.8, 0.2, 0.6
    else:
        up = seg(t, B("b7"), BE("b9")) * 0.45 + lift * 0.55
        kx = lerp(fx - 140, 790, up) + math.sin(t * 1.3) * 14 * up
        ky = lerp(ground(fx - 140), 860, up) + math.sin(t * 1.9) * 12 * up
        rot, wind_k, sag = lerp(1.25, -0.15, ease(clamp(up * 2))), 0.3 + 0.7 * up, 1 - up
    # string
    ctx.move_to(hx_, hy_)
    mx, my = (hx_ + kx) / 2, (hy_ + ky) / 2 + 60 * sag + 10
    ctx.curve_to(mx, my, mx, my, kx, ky + 30)
    rgb(ctx, hx("#E8D9C0"), 0.7)
    ctx.set_line_width(1.6)
    ctx.stroke()
    glow(ctx, kx, ky, 160, C["gold"], 0.3 * lift)
    kite_shape(ctx, kx, ky, 112, rot, t, wind_k)

    if dim:
        ctx.set_source_rgba(0.02, 0.02, 0.05, 0.3 * dim)
        ctx.paint()
    label(ctx, "John 3:8", "The wind bloweth where it listeth", t, B("b8")) if B("b8") <= t < BE("b10") else None


KITE = Reel("n1-holy-spirit-kite", "The Holy Spirit is the wind", [
    Beat("b0", "Trying harder won't lift you.", caption=False, hold=0.5),
    Beat("b1", "Ever tried to fly a kite with no wind?", ("wind",)),
    Beat("b2", "You run. You pull. You run faster."),
    Beat("b3", "It lifts for a second, then crashes.", ("crashes",), hold=0.3),
    Beat("b4", "A lot of us live the Christian life like that.", ("Christian",)),
    Beat("b5", "Running. Pulling. Crashing.", ("Crashing",)),
    Beat("b6", "But a kite was never meant to fly by effort.", ("effort",)),
    Beat("b7", "It was made to catch the wind.", ("wind",), hold=0.3),
    Beat("b8", "Jesus said the Spirit is like the wind.", ("Spirit",)),
    Beat("b9", "You can't see it. You can't control it."),
    Beat("b10", "But you can see what it lifts.", ("lifts",), hold=0.6),
    Beat("b11", "The Holy Spirit isn't the reward for trying harder.", ("harder",)),
    Beat("b12", "He's the wind.", ("wind",), hold=0.4),
    Beat("b13", "Stop running. Let him lift you.", ("lift",), hold=1.0),
], draw_kite, ("TRYING HARDER", "WON'T LIFT YOU"))


# =================================================================================== N2 stain
def shirt_path(ctx, cx, cy, s):
    ctx.move_to(cx - 95 * s, cy - 200 * s)
    ctx.curve_to(cx - 60 * s, cy - 170 * s, cx + 60 * s, cy - 170 * s, cx + 95 * s, cy - 200 * s)
    ctx.line_to(cx + 250 * s, cy - 130 * s)
    ctx.line_to(cx + 205 * s, cy - 20 * s)
    ctx.line_to(cx + 160 * s, cy - 45 * s)
    ctx.line_to(cx + 165 * s, cy + 250 * s)
    ctx.line_to(cx - 165 * s, cy + 250 * s)
    ctx.line_to(cx - 160 * s, cy - 45 * s)
    ctx.line_to(cx - 205 * s, cy - 20 * s)
    ctx.line_to(cx - 250 * s, cy - 130 * s)
    ctx.close_path()


def blob(ctx, x, y, r, seed, col, a):
    if r <= 0 or a <= 0:
        return
    for k, (rr, aa) in enumerate(((1.0, 1.0), (0.78, 0.6))):
        for i in range(73):
            th = i / 72 * math.tau
            q = rr * r * (1 + 0.17 * math.sin(3 * th + seed) + 0.09 * math.sin(7 * th + seed * 2) + 0.05 * math.sin(13 * th))
            (ctx.move_to if i == 0 else ctx.line_to)(x + q * math.cos(th), y + q * math.sin(th) * 0.9)
        ctx.close_path()
        rgb(ctx, col if k == 0 else hx("#7D1620"), a * aa)
        ctx.fill()


def draw_stain(r: Reel, ctx, t):
    B, BE = r.B, r.BE
    cx, cy = 540, 1170
    sky(ctx, "dark")
    clean = seg(t, B("b10"), BE("b10"))
    glow(ctx, cx, cy - 80, 760, C["sun"], 0.10 + 0.25 * clean)
    rays(ctx, cx, cy - 200, seg(t, B("b11"), BE("b11")), rot=t * 0.02, n=22)
    k = seg(t, B("b1"), B("b1") + 0.8)
    if k > 0:
        ctx.save()
        shirt_path(ctx, cx, cy, 1.6)
        rgb(ctx, C["shirt"], k)
        ctx.fill_preserve()
        ctx.clip()
        # fabric shading
        g = cairo.LinearGradient(cx - 300, 0, cx + 300, 0)
        g.add_color_stop_rgba(0, 0, 0, 0, 0.18)
        g.add_color_stop_rgba(0.5, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, 0.18)
        ctx.set_source(g)
        ctx.paint_with_alpha(k)
        # the stain: a drop, then spreading and smearing with every scrub
        land = B("b2") + 0.9
        rr = 0.0
        if t >= land:
            rr = 40 + 90 * seg(t, B("b4"), BE("b4")) + 50 * seg(t, B("b6"), BE("b6")) + 25 * seg(t, B("b7"), BE("b7"))
        fade = 1 - clean
        blob(ctx, cx + 10, cy + 10, rr, 1.3, hx("#A3202A"), fade)
        smear = seg(t, B("b7"), BE("b7"))
        blob(ctx, cx + 10 + 120 * smear, cy + 40 + 40 * smear, rr * 0.55 * smear, 4.1, hx("#A3202A"), 0.85 * fade)
        blob(ctx, cx - 90 * smear, cy - 50 * smear, rr * 0.4 * smear, 2.2, hx("#A3202A"), 0.75 * fade)
        ctx.restore()
        if clean > 0:
            glow(ctx, cx, cy, 420, hx("#FFFFFF"), 0.35 * clean * (1 - seg(t, BE("b10"), BE("b10") + 1.5) * 0.6))
    # the drop
    d0 = B("b2") + 0.2
    if d0 <= t < d0 + 0.7:
        u = (t - d0) / 0.7
        y = lerp(760, cy + 10, u * u)
        ctx.move_to(cx + 10, y - 26)
        ctx.curve_to(cx + 26, y + 6, cx + 22, y + 16, cx + 10, y + 16)
        ctx.curve_to(cx - 2, y + 16, cx - 6, y + 6, cx + 10, y - 26)
        rgb(ctx, hx("#B3232E"))
        ctx.fill()
    # the cloth, scrubbing
    on = seg(t, B("b3") + 0.3, B("b3") + 0.7) * (1 - seg(t, B("b8"), B("b8") + 0.6))
    if on > 0:
        busy = 1.0 if t < BE("b7") else 0.2
        ox = math.sin(t * 13) * 70 * busy
        oy = math.cos(t * 9) * 25 * busy
        ctx.save()
        ctx.translate(cx + 40 + ox, cy - 10 + oy)
        ctx.rotate(-0.25 + 0.1 * math.sin(t * 13))
        ctx.rectangle(-95, -60, 190, 120)
        rgb(ctx, hx("#8A8B92"), on)
        ctx.fill()
        for i in range(5):
            ctx.move_to(-95, -60 + i * 30)
            ctx.line_to(95, -60 + i * 30)
        rgb(ctx, hx("#6E6F76"), on)
        ctx.set_line_width(2)
        ctx.stroke()
        ctx.restore()
    # what we try
    tags_a = 1 - seg(t, B("b8"), B("b8") + 0.6)
    if tags_a > 0 and t >= B("b6"):
        ws = {w.w.strip(".").lower(): w.t0 for w in r.words if w.beat == "b6"}
        ctx.push_group()
        tag(ctx, "be nicer", 230, 790, t, ws["nicer"], strike_at=B("b7") + 0.3, rot=-0.06)
        tag(ctx, "more church", 840, 860, t, ws["church"], strike_at=B("b7") + 0.6, rot=0.05)
        tag(ctx, "cover it", 250, 1620, t, ws["cover"], strike_at=B("b7") + 0.9, rot=0.04)
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(tags_a)
    # snow
    sn = seg(t, B("b9"), B("b9") + 1.0)
    if sn > 0:
        rnd = random.Random(11)
        for i in range(120):
            x0, sp, sz = rnd.random() * W, 60 + rnd.random() * 90, 2 + rnd.random() * 4
            y = (rnd.random() * H + (t - B("b9")) * sp) % H
            x = x0 + math.sin(t * 0.8 + i) * 18
            rgb(ctx, C["white"], sn * (0.35 + 0.5 * rnd.random()))
            ctx.arc(x, y, sz, 0, math.tau)
            ctx.fill()
    if B("b9") <= t < BE("b11"):
        label(ctx, "Isaiah 1:18", "they shall be as white as snow", t, B("b9") + 1.0, y=1730)


STAIN = Reel("n2-sin-stain", "You can't scrub this stain out", [
    Beat("b0", "You can't scrub this stain out.", caption=False, hold=0.5),
    Beat("b1", "Picture a white shirt.", ("white",)),
    Beat("b2", "One drop of red dye.", ("red",), hold=0.5),
    Beat("b3", "You grab a cloth and scrub."),
    Beat("b4", "It doesn't come out. It spreads.", ("spreads",)),
    Beat("b5", "That's what we do with sin.", ("sin",)),
    Beat("b6", "We scrub harder. Be nicer. Go to church more. Try to cover it."),
    Beat("b7", "But scrubbing doesn't remove a stain. It just moves it around.", ("moves",)),
    Beat("b8", "God never asked you to clean yourself up.", ("God",), hold=0.3),
    Beat("b9", "Isaiah says, though your sins be as scarlet, they shall be as white as snow.", ("scarlet", "snow")),
    Beat("b10", "Not lighter. Not hidden. White.", ("White",), hold=0.5),
    Beat("b11", "That's what Jesus does with the stain you can't get out.", ("Jesus",), hold=1.0),
], draw_stain, ("YOU CAN'T SCRUB", "THIS STAIN OUT"))


# =================================================================================== N3 receipt
def bill(ctx, t, r: Reel, cx, top, length, n_red, owed, stamp, glow_k, scale=1.0):
    ctx.save()
    ctx.translate(cx, top)
    ctx.scale(scale, scale)
    w = 520
    glow(ctx, 0, length / 2, 600, C["gold"], 0.35 * glow_k)
    ctx.rectangle(-w / 2 + 8, 12, w, length)
    rgb(ctx, C["ink"], 0.5)
    ctx.fill()
    ctx.rectangle(-w / 2, 0, w, length)
    rgb(ctx, C["paper"])
    ctx.fill()
    text(ctx, "ACCOUNT", 0, 58, 26, hx("#3A2E22"), 0.9, spacing=6)
    rgb(ctx, C["paper_line"])
    ctx.set_line_width(1.5)
    ctx.move_to(-w / 2 + 40, 80)
    ctx.line_to(w / 2 - 40, 80)
    ctx.stroke()
    rows = int((length - 200) / 34)
    for i in range(max(rows, 0)):
        y = 115 + i * 34
        red = i >= rows - n_red
        ctx.move_to(-w / 2 + 50, y)
        ctx.line_to(w / 2 - (150 if i % 3 else 110), y)
        rgb(ctx, C["red"] if red else C["paper_line"], 0.9 if red else 0.8)
        ctx.set_line_width(3 if red else 2)
        ctx.stroke()
    text(ctx, "OWED", -w / 2 + 50, length - 50, 26, hx("#3A2E22"), 0.9, align="left", spacing=4)
    text(ctx, f"{owed:,}", w / 2 - 50, length - 46, 44, C["red"] if owed else hx("#B8862F"), 1.0, align="right")
    if stamp > 0:
        s = lerp(2.2, 1.0, ease_out(clamp(stamp * 1.6)))
        ctx.save()
        ctx.translate(0, length * 0.48)
        ctx.rotate(-0.18)
        ctx.scale(s, s)
        a = clamp(stamp * 2)
        ctx.rectangle(-235, -62, 470, 124)
        rgb(ctx, hx("#B8862F"), a)
        ctx.set_line_width(7)
        ctx.stroke()
        text(ctx, "PAID IN FULL", 0, 18, 50, hx("#B8862F"), a, spacing=3)
        ctx.restore()
    ctx.restore()


def draw_receipt(r: Reel, ctx, t):
    B, BE = r.B, r.BE
    cross_a = seg(t, B("b5"), B("b5") + 0.7) * (1 - seg(t, B("b7") - 0.2, B("b7") + 0.3))
    greek_a = seg(t, B("b7") - 0.2, B("b7") + 0.3) * (1 - seg(t, B("b8") - 0.3, B("b8") + 0.3))
    bill_a = 1 - cross_a - greek_a

    def bill_scene():
        sky(ctx, "dark")
        glow(ctx, 540, 1100, 700, C["sun"], 0.08 + 0.3 * seg(t, B("b11"), BE("b11")))
        rays(ctx, 540, 1050, seg(t, B("b11"), BE("b11")), rot=t * 0.02, n=20)
        length = 300 + 380 * seg(t, B("b2"), BE("b2")) + 120 * seg(t, B("b4"), BE("b4"))
        n_red = int(9 * seg(t, B("b3"), BE("b3")) + 4 * seg(t, B("b4"), BE("b4")))
        owed = int(480 + 2200 * seg(t, B("b2"), BE("b2")) + 9700 * seg(t, B("b4"), BE("b4")))
        paid_word = next(w.t0 for w in r.words if w.beat == "b9")
        stamp = ramp(t, paid_word - 0.05, 0.5)
        shrink = seg(t, B("b12") + 0.8, BE("b12"))
        if stamp >= 1:
            owed = int(owed * (1 - seg(t, paid_word + 0.7, paid_word + 1.6)))
        bill(ctx, t, r, 540, lerp(700, 860, shrink), length * lerp(1, 0.6, shrink), n_red, owed, stamp,
             seg(t, B("b11"), BE("b11")), scale=lerp(1.4, 1.25, shrink))

    def cross_scene():
        sky(ctx, "dusk")
        stars(ctx, t, 0.4)
        sun(ctx, 540, 1230, 50)
        rays(ctx, 540, 1230, 0.6, rot=t * 0.02)
        hill(ctx, 1320, 24, 1.1, 1.0, "#3B2A4C")
        ctx.move_to(0, H)
        ctx.line_to(0, 1480)
        ctx.curve_to(300, 1440, 380, 1240, 540, 1230)
        ctx.curve_to(700, 1240, 780, 1440, W, 1480)
        ctx.line_to(W, H)
        ctx.close_path()
        rgb(ctx, hx("#120E1C"))
        ctx.fill()
        for x, y, s in ((540, 1232, 1.0), (430, 1262, 0.72), (650, 1262, 0.72)):
            ctx.rectangle(x - 7 * s, y - 260 * s, 14 * s, 260 * s)
            ctx.rectangle(x - 62 * s, y - 205 * s, 124 * s, 13 * s)
            rgb(ctx, C["sil"])
            ctx.fill()
        label(ctx, "John 19:30", "It is finished", t, B("b5") + 0.8)

    def greek_scene():
        sky(ctx, "dark")
        greek_card(ctx, t, B("b7"), "τετέλεσται", "teh-TEL-es-tie",
                   "New Testament Greek")

    sky(ctx, "dark")
    layer(ctx, bill_a * seg(t, B("b1") - 0.2, B("b1") + 0.4), bill_scene)
    layer(ctx, cross_a, cross_scene)
    layer(ctx, greek_a, greek_scene)


RECEIPT = Reel("n3-cross-paid-in-full", "One Greek word changes everything", [
    Beat("b0", "One Greek word changes everything.", caption=False, hold=0.5),
    Beat("b1", "Imagine a debt you could never pay.", ("debt",)),
    Beat("b2", "Every month the bill gets longer.", ("longer",)),
    Beat("b3", "Every mistake adds a line.", ("line",)),
    Beat("b4", "You work harder, but the number only grows.", ("grows",), hold=0.3),
    Beat("b5", "On the cross, Jesus cried out, it is finished.", ("finished",)),
    Beat("b6", "John writes it as one Greek word."),
    Beat("b7", "Tetelestai.", ("Tetelestai",), hold=0.9),
    Beat("b8", "In everyday Greek, it was used when a debt was paid.", ("paid",)),
    Beat("b9", "Paid in full.", ("Paid", "full"), hold=0.4),
    Beat("b10", "Not paid in part. Not paid if you behave. Paid.", ("Paid",)),
    Beat("b11", "That's grace.", ("grace",), hold=0.4),
    Beat("b12", "You don't work off the bill. You receive the receipt.", ("receipt",), hold=1.0),
], draw_receipt, ("ONE GREEK WORD", "CHANGES EVERYTHING"))


# =================================================================================== N4 bridge
EDGE_L, EDGE_R, TOP = 380, 700, 1200


def cliffs(ctx):
    # canyon depth
    g = cairo.LinearGradient(0, TOP, 0, H)
    g.add_color_stop_rgb(0, *hx("#2A1F38"))
    g.add_color_stop_rgb(1, *hx("#050409"))
    ctx.rectangle(EDGE_L - 40, TOP - 10, EDGE_R - EDGE_L + 80, H)
    ctx.set_source(g)
    ctx.fill()
    for side in (-1, 1):
        ctx.move_to(0 if side < 0 else W, H)
        edge = EDGE_L if side < 0 else EDGE_R
        x0 = 0 if side < 0 else W
        ctx.line_to(x0, TOP - 10)
        steps = 12
        for i in range(steps + 1):
            x = lerp(x0, edge, i / steps)
            ctx.line_to(x, TOP + 6 * math.sin(i * 1.7 + side))
        for i in range(10):
            y = TOP + i * 75
            ctx.line_to(edge + side * (18 * math.sin(i * 2.1) - 6 * i), y)
        ctx.line_to(edge - side * 140, H)
        ctx.close_path()
        rgb(ctx, hx("#100C18"))
        ctx.fill()


def draw_bridge(r: Reel, ctx, t):
    B, BE = r.B, r.BE
    sky(ctx, "dusk")
    stars(ctx, t, 0.45)
    hill(ctx, 1260, 40, 1.6, 0.4, "#3B2A4C")
    hill(ctx, 1300, 24, 0.8, 2.2, "#271C36")
    god = seg(t, B("b2"), BE("b2"))
    pulse = 1 + 0.25 * seg(t, B("b7"), B("b7") + 0.6) * math.sin((t - B("b7")) * 5) ** 2
    glow(ctx, 900, TOP - 40, 520 * pulse, C["sun"], 0.45 * god)
    rays(ctx, 900, TOP - 40, god * (0.6 + 0.4 * seg(t, B("b12"), BE("b12"))), rot=t * 0.03)
    cliffs(ctx)
    glow(ctx, 900, TOP - 10, 240, C["gold"], 0.25 * god)

    # attempts that fall short
    attempts = [("good deeds", 470, "b4", 0), ("religion", 540, "b4", 1), ("better than most", 600, "b4", 2),
                (None, 640, "b5", 0), (None, 668, "b5", 1)]
    fade = 1 - seg(t, B("b8"), B("b8") + 0.8)
    b4w = [w.t0 for w in r.words if w.beat == "b4"]
    starts = [B("b3") + 0.4, b4w[2] if len(b4w) > 2 else B("b4"), b4w[3] if len(b4w) > 3 else B("b4") + 1]
    for i, (lab, land, beat, k) in enumerate(attempts):
        t0 = (starts[k] if beat == "b4" else B("b5") + 0.4 + 0.5 * k)
        if i == 0:
            t0 = B("b3") + 0.4
        p = ease_out(ramp(t, t0, 0.9))
        if p <= 0 or fade <= 0:
            continue
        x0, y0 = EDGE_L - 30, TOP - 40
        ctx.set_dash([10, 9])
        n = 40
        for j in range(int(n * p) + 1):
            u = j / n
            x = lerp(x0, land, u)
            y = y0 - 210 * math.sin(u * math.pi * 0.62) + 380 * max(0, u - 0.62) ** 1.5 * 3
            (ctx.move_to if j == 0 else ctx.line_to)(x, y)
        rgb(ctx, C["white"], 0.6 * fade)
        ctx.set_line_width(3)
        ctx.stroke()
        ctx.set_dash([])
        if lab:
            tag(ctx, lab, lerp(x0, land, 0.4) + (i - 1) * 40, y0 - 250 - i * 70, t, t0 + 0.3, rot=-0.05 + 0.04 * i)
    # the gap
    gk = seg(t, B("b6"), B("b6") + 0.6) * fade
    if gk > 0:
        rgb(ctx, C["gold"], gk)
        ctx.set_line_width(2)
        y = TOP + 120
        ctx.move_to(EDGE_L + 10, y)
        ctx.line_to(EDGE_R - 10, y)
        ctx.stroke()
        text(ctx, "the gap", (EDGE_L + EDGE_R) / 2, y + 44, 34, C["gold"], gk, italic=True)

    # the cross rises in the gap; its crossbar becomes the bridge
    c0 = B("b8")
    up = seg(t, c0, c0 + 1.6)
    bar_w = EDGE_R - EDGE_L + 70
    if up > 0:
        post_top, post_len = 240, 900
        bar_y = lerp(H + 300, TOP - 2, up)          # top of the crossbar
        cx = (EDGE_L + EDGE_R) / 2
        glow(ctx, cx, bar_y, 300, C["gold"], 0.4 * up)
        ctx.rectangle(cx - 15, bar_y - post_top, 30, post_len)
        ctx.rectangle(cx - bar_w / 2, bar_y, bar_w, 28)
        rgb(ctx, hx("#1A1424"))
        ctx.fill_preserve()
        rgb(ctx, C["gold"], 0.55 * up)
        ctx.set_line_width(2)
        ctx.stroke()

    # you
    walk = seg(t, B("b11"), BE("b12") - 0.6)
    fx = lerp(EDGE_L - 60, 880, walk)
    fy = TOP + 2
    jump = 0.0
    for t0 in starts[:1]:
        jump = math.sin(clamp((t - t0) / 0.5) * math.pi) * 40 if t0 <= t < t0 + 0.5 else jump
    person(ctx, fx, fy - jump, 220, step=math.sin(t * 9) * (0 < walk < 1), lean=0.1 * (0 < walk < 1),
           look_up=god * 0.5, rim=walk)
    if B("b9") <= t < BE("b10"):
        label(ctx, "John 14:6", "I am the way, the truth, and the life", t, B("b9") + 0.3)


BRIDGE = Reel("n4-jesus-the-way-bridge", "There's a gap no one can jump", [
    Beat("b0", "There's a gap no one can jump.", caption=False, hold=0.5),
    Beat("b1", "Picture a canyon.", ("canyon",)),
    Beat("b2", "You on one side. God on the other.", ("God",), hold=0.3),
    Beat("b3", "Some people try to jump it.", ("jump",), hold=0.6),
    Beat("b4", "Good deeds. Religion. Being better than most.", hold=0.8),
    Beat("b5", "Some jump further than others.", hold=0.8),
    Beat("b6", "But nobody makes it across. The gap is too wide.", ("gap",)),
    Beat("b7", "So God didn't shout instructions from the other side."),
    Beat("b8", "He built a bridge.", ("bridge",), hold=1.6),
    Beat("b9", "Jesus said, I am the way.", ("way",)),
    Beat("b10", "Not a way. Not one of many good tips. The way.", ("way",)),
    Beat("b11", "The bridge isn't how far you can jump.", ("bridge",)),
    Beat("b12", "It's who you trust to carry you across.", ("trust",), hold=1.6),
], draw_bridge, ("THERE'S A GAP", "NO ONE CAN JUMP"))

ALL = {r.slug: r for r in (KITE, STAIN, RECEIPT, BRIDGE)}
