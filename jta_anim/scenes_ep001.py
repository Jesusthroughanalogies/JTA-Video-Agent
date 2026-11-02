"""Ep 1 animation scenes, one per [ANIM] and [TEXT] shot in episodes/ep001/shots.py.

Every scene is drawn by a function registered with @scene("<shot id>"). The agent calls
render_shot() with the shot's slot length and its narration word times (from the aligned
timeline), so beats land on the words. Without word times the line is spread evenly.

Run a preview of everything:  python -m jta_anim.scenes_ep001 OUT_DIR [shot id ...]
"""
from __future__ import annotations

import math
import random
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cairo

from . import cast, egypt
from . import props as P
from .core import (back, cached, caption, clamp, diamond, ease_in_out, ease_out, finish, label, lerp,
                   outline_fill, pop, ramp, rgb, rounded_rect, text, text_width)
from .theme import C, FPS, H, OUTLINE, W

# ---------------------------------------------------------------- framework


@dataclass
class Shot:
    id: str
    dur: float
    line: str = ""
    words: list = field(default_factory=list)   # [(word, start seconds from shot start)]

    def __post_init__(self):
        if not self.words and self.line and not self.line.startswith("("):
            ws = self.line.split()
            span = max(self.dur - 0.5, 0.5)
            self.words = [(w, 0.15 + i * span / len(ws)) for i, w in enumerate(ws)]

    def at(self, frac: float) -> float:
        return frac * self.dur

    def wt(self, key: str, frac: float) -> float:
        """Start time of the first word beginning with key (case-insensitive), else frac of the shot."""
        key = key.lower()
        for w, t0 in self.words:
            if w.lower().strip("\"'.,?!:;()‘’“”").startswith(key):
                return t0
        return self.at(frac)


@dataclass
class Scene:
    draw: Callable
    base: str = "day"            # day | night | space | overlay
    captions: bool = True
    gold: tuple = ()


REG: dict[str, Scene] = {}


def scene(*ids: str, base: str = "day", captions: bool = True, gold: tuple = ()):
    def deco(fn):
        for i in ids:
            REG[i] = Scene(fn, base, captions, gold)
        return fn
    return deco


_BG: dict = {}


def _base(ctx, kind):
    if kind not in _BG:
        _BG[kind] = cached({"day": lambda c: egypt.background(c),
                            "night": lambda c: egypt.background(c, night=True),
                            "space": egypt.space}[kind])
    ctx.set_source_surface(_BG[kind], 0, 0)
    ctx.paint()


def _chunks(words, max_words=9):
    """Split the line into caption chunks at punctuation, at most max_words each."""
    out, cur = [], []
    for w, t0 in words:
        cur.append((w, t0))
        if len(cur) >= max_words or (w[-1:] in ".?!;:" and len(cur) >= 3):
            out.append(cur)
            cur = []
    if cur:
        if out and len(cur) < 3:
            out[-1].extend(cur)
        else:
            out.append(cur)
    return out


def _caption(ctx, s: Shot, t: float, gold):
    if not s.words:
        return
    chunks = _chunks(s.words)
    cur = chunks[0]
    for c in chunks:
        if t >= c[0][1] - 0.05:
            cur = c
    caption(ctx, cur, t, gold=gold)


def draw_frame(ctx, shot: Shot, t: float, sc: Scene, overlay: bool = False):
    if sc.base != "overlay":
        _base(ctx, sc.base)
    elif not overlay:          # an overlay card previewed without its AI background
        _base(ctx, "night")
    sc.draw(ctx, t, shot)
    if sc.captions:
        _caption(ctx, shot, t, sc.gold)


def render_shot(shot_id: str, seconds: float, out: Path, *, line: str = "", words=None,
                bg_video: Optional[Path] = None, still_at: Optional[float] = None) -> Path:
    """Render one shot to MP4 (or a PNG still). TEXT cards with an AI background are drawn
    with transparency and composited over the graded clip."""
    sc = REG[shot_id]
    shot = Shot(shot_id, seconds, line, list(words or []))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    overlay = sc.base == "overlay" and bg_video is not None and Path(bg_video).exists()

    def frame(i):
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.restore()
        t = i / FPS
        draw_frame(ctx, shot, t, sc, overlay)
        finish(ctx, i, vignette=0.0 if overlay else 0.35)
        surf.flush()

    if still_at is not None:
        frame(int(still_at * FPS))
        surf.write_to_png(str(out))
        return out
    n = max(1, int(round(seconds * FPS)))
    if overlay:
        cmd = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(bg_video),
               "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-filter_complex",
               f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
               f"eq=brightness=-0.06,setsar=1[b];[b][1:v]overlay=alpha=premultiplied:shortest=1,format=yuv420p",
               "-t", f"{seconds:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-pix_fmt", "yuv420p", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            frame(i)
            p.stdin.write(bytes(surf.get_data()))
    except BrokenPipeError:
        pass
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")
    return out


def section_label(ctx, s, t, txt, fade_out=None):
    a = ramp(t, 0.05, 0.4)
    if fade_out is not None:
        a *= 1 - ramp(t, fade_out, 0.4)
    label(ctx, txt, W / 2, 190, 34, alpha=a, grow=ease_out(ramp(t, 0.15, 0.7)))


def word_label(ctx, txt, x, y, t, t0, size=40, col=C["ink"], a=1.0):
    k = ramp(t, t0, 0.25)
    text(ctx, txt, x, y, size, col, spacing=size * 0.18, alpha=k * a, scale=pop(t, t0, 0.35), shadow=True)


# ================================================================ HOOK

def _search_bar(ctx, t, s, typed: str, cursor=True, impact=0.0):
    x0, x1, yc, hh = 420, 1500, 470, 120
    a = ease_out(ramp(t, 0.0, 0.4))
    sc = pop(t, 0.0, 0.45) * (1 + 0.04 * impact)
    ctx.save()
    ctx.translate(W / 2, yc)
    ctx.scale(sc, sc)
    ctx.translate(-W / 2, -yc)
    if impact:
        P.glow(ctx, W / 2, yc, 700, C["gold"], 0.35 * impact)
    rounded_rect(ctx, x0 + 8, yc - hh / 2 + 10, x1 - x0, hh, hh / 2)
    rgb(ctx, C["ink"], 0.18 * a)
    ctx.fill()
    rounded_rect(ctx, x0, yc - hh / 2, x1 - x0, hh, hh / 2)
    outline_fill(ctx, C["papyrus"], a=a)
    rounded_rect(ctx, x0 + 12, yc - hh / 2 + 12, x1 - x0 - 24, hh - 24, hh / 2 - 12)
    rgb(ctx, C["gold"], a)
    ctx.set_line_width(2)
    ctx.stroke()
    ctx.arc(x0 + 82, yc - 6, 22, 0, 2 * math.pi)        # magnifying glass
    rgb(ctx, C["ink"], a)
    ctx.set_line_width(6)
    ctx.stroke()
    ctx.move_to(x0 + 98, yc + 10)
    ctx.line_to(x0 + 116, yc + 28)
    ctx.stroke()
    w = text(ctx, typed, x0 + 150, yc + 18, 52, C["ink"], align="left", alpha=a) if typed else 0
    if cursor and int(t * 2.2) % 2 == 0:
        ctx.rectangle(x0 + 156 + w, yc - 30, 4, 58)
        rgb(ctx, C["ink"], a)
        ctx.fill()
    ctx.restore()


def _typed(phrase, t, t_in, t_out, t_del, t_gone):
    n = len(phrase)
    if t < t_in:
        return ""
    if t < t_out:
        return phrase[: int(n * ramp(t, t_in, t_out - t_in))]
    if t < t_del:
        return phrase
    return phrase[: int(n * (1 - ramp(t, t_del, t_gone - t_del)))]


@scene("H-02", captions=False)
def h02(ctx, t, s):
    d = s.dur
    a = _typed("which church should I go to", t, 0.1 * d, 0.32 * d, 0.38 * d, 0.46 * d)
    b = _typed("how do I pray", t, 0.55 * d, 0.72 * d, 0.84 * d, 0.92 * d)
    _search_bar(ctx, t, s, a or b)


@scene("H-03", captions=False)
def h03(ctx, t, s):
    d = s.dur
    t_end = 0.45 * d
    typed = "IS THERE A GOD?"[: int(15 * ramp(t, 0.08 * d, t_end - 0.08 * d))]
    imp = math.exp(-max(t - t_end, 0) * 3) if t >= t_end else 0.0
    _search_bar(ctx, t, s, typed, impact=imp)
    if t >= t_end:  # ripple rings out from the bar
        for k in range(3):
            u = ramp(t, t_end + k * 0.15, 1.2)
            if 0 < u < 1:
                rounded_rect(ctx, 420 - 200 * u, 410 - 60 * u, 1080 + 400 * u, 120 + 120 * u, 60 + 60 * u)
                rgb(ctx, C["gold"], 0.6 * (1 - u))
                ctx.set_line_width(4)
                ctx.stroke()


@scene("H-08", gold=("three", "biggest"))
def h08(ctx, t, s):
    sts = []
    for k in range(3):
        u = ease_out(ramp(t, 0.2 + k * 0.25, 0.6))
        sts.append({"y": P.FRAME_Y + (1 - u) * 700, "alpha": u})
    P.triptych(ctx, sts)


@scene("H-09", gold=("dominoes.", "dials.", "painting."))
def h09(ctx, t, s):
    keys = (("domino", 0.12), ("dial", 0.45), ("painting", 0.78))
    sts = []
    for k, (w, f) in enumerate(keys):
        t0 = s.wt(w, f)
        sts.append({"fill": ease_out(ramp(t, t0, 0.4)), "lit": 0.6 * math.exp(-max(t - t0, 0) * 2) * (t >= t0),
                    "title": ramp(t, t0 + 0.2, 0.4)})
    P.triptych(ctx, sts)


@scene("H-10", base="overlay", captions=False)
def h10(ctx, t, s):
    a = ease_out(ramp(t, 0.1, 0.5))
    rgb(ctx, C["night_bg"], 0.35 * a)
    ctx.paint()
    text(ctx, "IS THERE A GOD?", W / 2, H / 2 + 30, 130, C["night_text"], spacing=14, alpha=a,
         scale=lerp(1.12, 1.0, ease_out(ramp(t, 0.1, 1.2))), shadow=True)
    for side in (-1, 1):
        g = ease_out(ramp(t, 0.5, 0.8))
        x0 = W / 2 + side * 140
        ctx.move_to(x0, H / 2 + 110)
        ctx.line_to(x0 + side * 360 * g, H / 2 + 110)
        rgb(ctx, C["gold"], a)
        ctx.set_line_width(3)
        ctx.stroke()
        diamond(ctx, x0 + side * (360 * g + 14), H / 2 + 110, 8, C["gold"], a * g)
    diamond(ctx, W / 2, H / 2 + 110, 10, C["gold"], a)


# ================================================================ PART 1: the dominoes

N_DOM, GAP, X0, BASE = 11, 100, 400, 790


def _fall_angles(t, t0, step=0.2, n=N_DOM, last_flat=True):
    rest = P.domino_rest(GAP)
    out = []
    for i in range(n):
        ts = t0 + i * step
        last = i == n - 1 and last_flat
        target = math.pi / 2 if last else rest
        u = ramp(t, ts, 0.45 if last else 0.26)
        a = target * (u * u)
        if last and u >= 1:
            a = target - 0.06 * math.sin(min((t - ts - 0.45) * 18, math.pi)) * math.exp(-(t - ts - 0.45) * 4)
        out.append(a)
    return out


@scene("P1-01", gold=("dominoes",))
def p101(ctx, t, s):
    section_label(ctx, s, t, "Picture 1 · the dominoes")
    P.ledge(ctx, X0 - 70, BASE, N_DOM * GAP + 120)
    t0 = max(s.wt("falling", 0.25), 0.8)
    angles = _fall_angles(t, t0, step=min(0.2, (s.dur - t0 - 0.6) / N_DOM))
    for i in range(N_DOM):
        enter = pop(t, 0.2 + i * 0.05, 0.3)
        ctx.save()
        ctx.translate(0, (1 - enter) * 40)
        P.domino(ctx, X0 + i * GAP, BASE, angles[i], alpha=clamp(enter))
        ctx.restore()


@scene("P1-02", gold=("backwards.", "further."))
def p102(ctx, t, s):
    # the camera pulls back along the fallen line: it stretches to the horizon both ways
    u = ease_in_out(ramp(t, 0.2, s.dur - 0.4))
    zoom = lerp(1.0, 0.28, u)
    pan = lerp(0, 2600, u * u)
    rest = P.domino_rest(GAP)
    ctx.save()
    ctx.translate(W / 2, BASE)
    ctx.scale(zoom, zoom)
    ctx.translate(-W / 2 + pan, -BASE)
    n0 = int((-pan - W / zoom) / GAP) - 2
    n1 = int((W / zoom + 400 - pan) / GAP) + 2
    ctx.rectangle(X0 + n0 * GAP, BASE, (n1 - n0) * GAP, 26)
    outline_fill(ctx, C["stone_shade"])
    for i in range(n0, n1):
        P.domino(ctx, X0 + i * GAP, BASE, rest)
    ctx.restore()
    for k in range(2):  # speed streaks
        a = 0.25 * u
        y = 560 + k * 90
        ctx.move_to(250, y)
        ctx.line_to(250 + 500 * u, y)
        rgb(ctx, C["ink"], a)
        ctx.set_line_width(2)
        ctx.stroke()


@scene("P1-03", gold=("first", "one?"))
def p103(ctx, t, s):
    rest = P.domino_rest(GAP)
    spot = ease_in_out(ramp(t, s.wt("something", 0.45), 0.8))
    P.ledge(ctx, X0 - 70, BASE, N_DOM * GAP + 120)
    for i in range(N_DOM):
        first = i == 0
        P.domino(ctx, X0 + i * GAP, BASE, 0.0 if first else rest,
                 alpha=1.0 if first else 1 - 0.6 * spot, glow_a=spot if first else 0.0)
    if spot > 0:  # beam of light from above onto the first domino
        ctx.move_to(X0 - 20, 120)
        ctx.line_to(X0 + 70, 120)
        ctx.line_to(X0 + 140, BASE)
        ctx.line_to(X0 - 90, BASE)
        ctx.close_path()
        g = cairo.LinearGradient(0, 120, 0, BASE)
        g.add_color_stop_rgba(0, *C["sun"], 0.0)
        g.add_color_stop_rgba(1, *C["sun"], 0.35 * spot)
        ctx.set_source(g)
        ctx.fill()


GAL = [(random.Random(i).uniform(0, 2 * math.pi), random.Random(i * 7 + 1).uniform(0.15, 1.0),
        random.Random(i * 13 + 2).uniform(10, 34)) for i in range(70)]


def _galaxies(ctx, t, spread, a=1.0, cx=W / 2, cy=H / 2 - 40):
    for i, (ang, d, r) in enumerate(GAL):
        dist = d * spread * 900
        x = cx + math.cos(ang) * dist * 1.25
        y = cy + math.sin(ang) * dist * 0.62
        P.galaxy(ctx, x, y, r * clamp(spread * 3), rot=t * 0.15 + i, a=a, seed=i)


@scene("P1-07", base="space", gold=("beginning,", "13.8", "billion"))
def p107(ctx, t, s):
    t_b = s.wt("beginning", 0.35)
    P.glow(ctx, W / 2, H / 2 - 40, 60 + 30 * math.sin(t * 6), C["night_text"], 0.9 * (1 - ramp(t, t_b, 0.6)))
    P.glow(ctx, W / 2, H / 2 - 40, 14, C["papyrus"], 1.0 - ramp(t, t_b, 0.3))
    if t >= t_b:
        u = ramp(t, t_b, 0.5)
        P.glow(ctx, W / 2, H / 2 - 40, 1200 * ease_out(u), C["sun"], 0.8 * (1 - u))  # flash
        _galaxies(ctx, t, ease_out(ramp(t, t_b, s.dur - t_b + 0.5)) * 0.85)


@scene("P1-07a", base="space", gold=("backwards,", "one", "starting", "point."))
def p107a(ctx, t, s):
    t_r = s.wt("run", 0.5)
    if t < t_r:
        spread = 0.85 + 0.12 * ramp(t, 0, t_r)
    else:
        spread = lerp(0.97, 0.0, ease_in_out(ramp(t, t_r + 0.2, s.dur - t_r - 0.6)))
        word_label(ctx, "RUN IT BACKWARDS", W / 2, 200, t, t_r, size=36, col=C["night_text"])
    _galaxies(ctx, t, spread)
    if spread < 0.05:
        P.glow(ctx, W / 2, H / 2 - 40, 90, C["papyrus"], 1.0)


@scene("P1-07b", base="space", gold=("afterglow",))
def p107b(ctx, t, s):
    t_g = s.wt("glow", 0.3)
    a = ease_out(ramp(t, t_g, 1.4))
    cx, cy, rx, ry = W / 2, H / 2 - 50, 620, 300
    ctx.save()
    P.ellipse(ctx, cx, cy, rx, ry)
    ctx.clip()
    rgb(ctx, C["sun"], 0.38 * a)
    ctx.paint()
    rnd = random.Random(3)
    for _ in range(260):  # mottled, almost even glow
        x, y = rnd.uniform(cx - rx, cx + rx), rnd.uniform(cy - ry, cy + ry)
        col = C["sun"] if rnd.random() > 0.5 else C["terracotta"]
        P.glow(ctx, x, y, rnd.uniform(40, 110), col, 0.12 * a)
    ctx.restore()
    P.ellipse(ctx, cx, cy, rx, ry)
    rgb(ctx, C["gold"], a)
    ctx.set_line_width(3)
    ctx.stroke()
    t_l = s.wt("afterglow", 0.65)
    k = ramp(t, t_l, 0.4)
    label(ctx, "The afterglow · 1965", W / 2, cy + ry + 70, 34, alpha=k, grow=ease_out(ramp(t, t_l + 0.1, 0.6)),
          col=C["night_text"])


ORBIT_WORDS = ("SPACE", "TIME", "MATTER", "ENERGY")


def _burst(ctx, t, cx, cy, a=1.0):
    P.glow(ctx, cx, cy, 260, C["sun"], 0.55 * a)
    P.glow(ctx, cx, cy, 60, C["papyrus"], 0.95 * a)
    for k in range(16):
        ang = k * math.pi / 8 + t * 0.2
        ctx.move_to(cx + math.cos(ang) * 70, cy + math.sin(ang) * 70)
        ctx.line_to(cx + math.cos(ang) * (190 + 30 * math.sin(t * 3 + k)), cy + math.sin(ang) * (190 + 30 * math.sin(t * 3 + k)))
        rgb(ctx, C["sun"], 0.5 * a)
        ctx.set_line_width(3)
        ctx.stroke()


def _orbit_words(ctx, t, s, a_all=1.0, cx=W / 2, cy=H / 2 - 40):
    for k, w in enumerate(ORBIT_WORDS):
        t0 = s.wt(w.lower(), 0.1 + k * 0.18)
        ang = t * 0.45 + k * math.pi / 2
        x, y = cx + math.cos(ang) * 470, cy + math.sin(ang) * 230
        word_label(ctx, w, x, y + 14, t, t0, size=46, col=C["night_text"], a=a_all)


@scene("P1-08", base="space", gold=("starting.",))
def p108(ctx, t, s):
    _burst(ctx, t, W / 2, H / 2 - 40)
    _orbit_words(ctx, t, s)


@scene("P1-09", gold=("cause,", "cause."))
def p109(ctx, t, s):
    steps = (("Everything that begins has a cause", "begins", 0.05),
             ("The universe began", "universe", 0.4),
             ("So the universe had a cause", "then", 0.72))
    for k, (txt, key, f) in enumerate(steps):
        t0 = s.wt(key, f) if k else s.at(0.05)
        u = ease_out(ramp(t, t0, 0.45))
        y = 300 + k * 180
        if u <= 0:
            continue
        pw = 1000
        rounded_rect(ctx, W / 2 - pw / 2, y - 60 + (1 - u) * 30, pw, 100, 14)
        outline_fill(ctx, C["papyrus"] if k < 2 else C["gold"], a=u)
        text(ctx, txt, W / 2, y + 8 + (1 - u) * 30, 46, C["ink"], alpha=u)
        text(ctx, str(k + 1), W / 2 - pw / 2 + 50, y + 8, 40, C["bronze"], alpha=u)
        if k:
            P.arrow(ctx, W / 2, y - 120, W / 2, y - 68, C["bronze"], 5, 16, a=u, p=u)


@scene("P1-10", base="space", gold=("made",))
def p110(ctx, t, s):
    fade = ease_in_out(ramp(t, s.at(0.15), 1.0))
    _burst(ctx, t, W / 2 - 160, H / 2 - 40, 1 - 0.6 * fade)
    for k, w in enumerate(ORBIT_WORDS):
        ang = t * 0.45 + k * math.pi / 2
        x, y = W / 2 - 160 + math.cos(ang) * 400, H / 2 - 40 + math.sin(ang) * 200
        text(ctx, w, x, y + 14, 46, C["night_text"], spacing=8, alpha=1 - fade)
    # the frame of the universe, and one point of light outside it
    fa = ease_out(ramp(t, s.at(0.3), 0.8))
    rounded_rect(ctx, 330, 230, 1000, 520, 20)
    rgb(ctx, C["gold"], 0.8 * fa)
    ctx.set_line_width(4)
    ctx.set_dash([18, 12])
    ctx.stroke()
    ctx.set_dash([])
    text(ctx, "THE UNIVERSE", 830, 290, 30, C["night_text"], spacing=8, alpha=fa)
    t_p = s.wt("because", 0.55)
    pa = ease_out(ramp(t, t_p, 0.8))
    pulse = 1 + 0.15 * math.sin(t * 4)
    P.glow(ctx, 1520, H / 2 - 40, 150 * pulse, C["sun"], 0.7 * pa)
    P.glow(ctx, 1520, H / 2 - 40, 26, C["papyrus"], pa)


@scene("P1-12T", base="overlay", captions=False)
def p112t(ctx, t, s):
    P.verse_card(ctx, t, "In the beginning God created the heavens and the earth.", "Genesis 1:1 · NIV",
                 gold=("god", "created"), per_word=min(0.22, s.dur * 0.6 / 10))


def _first_domino_scene(ctx, t, spot=1.0):
    rest = P.domino_rest(GAP)
    P.ledge(ctx, X0 - 70, BASE, N_DOM * GAP + 120)
    for i in range(N_DOM):
        P.domino(ctx, X0 + i * GAP, BASE, 0.0 if i == 0 else rest, alpha=1.0 if i == 0 else 1 - 0.6 * spot,
                 glow_a=spot if i == 0 else 0.0)


@scene("P1-13", gold=("made", "God?\""))
def p113(ctx, t, s):
    _first_domino_scene(ctx, t)
    t0 = s.wt("then", 0.35)
    u = ramp(t, t0, 0.5)
    y = lerp(-100, 590, u * u)
    if t > t0 + 0.5:  # bounce and settle
        y = 590 - 60 * abs(math.sin((t - t0 - 0.5) * 7)) * math.exp(-(t - t0 - 0.5) * 4)
    question_mark = P.question_mark
    question_mark(ctx, X0 + 23, y, 170, rot=0.1 * math.sin(t * 3) * (t > t0))


@scene("P1-14", gold=("eternal.", "begin,", "cause."))
def p114(ctx, t, s):
    y_line, y_band = 640, 400
    x_start, x_now = 640, 1540
    u = ease_out(ramp(t, 0.2, 1.0))
    ctx.move_to(x_start, y_line)
    ctx.line_to(lerp(x_start, x_now, u), y_line)
    rgb(ctx, C["ink"])
    ctx.set_line_width(6)
    ctx.stroke()
    ctx.arc(x_start, y_line, 14, 0, 2 * math.pi)
    outline_fill(ctx, C["terracotta"], a=ramp(t, 0.1, 0.3))
    text(ctx, "THE UNIVERSE", (x_start + x_now) / 2, y_line - 30, 30, C["ink"], spacing=8, alpha=ramp(t, 0.6, 0.4))
    text(ctx, "IT BEGAN", x_start, y_line + 60, 26, C["terracotta"], spacing=6, alpha=ramp(t, 0.4, 0.4))
    text(ctx, "NOW", x_now, y_line + 60, 26, C["ink"], spacing=6, alpha=ramp(t, 1.0, 0.4))
    t_g = s.wt("eternal", 0.5)
    g = ease_in_out(ramp(t, t_g, 1.2))
    if g > 0:  # God: a band running beyond both ends of the frame
        grad = cairo.LinearGradient(160, 0, W - 160, 0)
        for stop, a in ((0, 0.0), (0.12, 1.0), (0.88, 1.0), (1, 0.0)):
            grad.add_color_stop_rgba(stop, *C["gold"], a * g)
        ctx.rectangle(lerp(W / 2, 160, g), y_band - 30, lerp(0, W - 320, g), 60)
        ctx.set_source(grad)
        ctx.fill()
        text(ctx, "GOD · NO BEGINNING, NO END", W / 2, y_band + 12, 32, C["ink"], spacing=6, alpha=ramp(t, t_g + 0.6, 0.4))
        for side in (-1, 1):
            P.arrow(ctx, W / 2 + side * 640, y_band + 70, W / 2 + side * 760, y_band + 70, C["gold"], 4, 14,
                    a=ramp(t, t_g + 0.8, 0.4))


@scene("P1-15", gold=("nature", "mind."))
def p115(ctx, t, s):
    ctx.move_to(W / 2, 120)
    ctx.line_to(W / 2, 860)
    rgb(ctx, C["ink"], 0.5)
    ctx.set_line_width(3)
    ctx.set_dash([12, 10])
    ctx.stroke()
    ctx.set_dash([])
    t_n = s.wt("blind", 0.55)
    t_m = s.wt("mind", 0.85)
    # left: a random swirl
    rnd = random.Random(5)
    for i in range(140):
        ang = rnd.uniform(0, 6.28) + t * rnd.uniform(-1.5, 1.5)
        rr = rnd.uniform(20, 260) * (1 + 0.15 * math.sin(t * 2 + i))
        x, y = 560 + math.cos(ang) * rr, 470 + math.sin(ang) * rr * 0.8
        rgb(ctx, (C["terracotta"], C["olive"], C["indigo"], C["bronze"])[i % 4], 0.75)
        ctx.arc(x, y, rnd.uniform(3, 8), 0, 2 * math.pi)
        ctx.fill()
    word_label(ctx, "BLIND NATURE", 560, 820, t, t_n, size=34)
    # right: a glowing hand withdrawing from the first domino
    tip = ease_out(ramp(t, 0.6, 0.6)) * 0.35
    P.domino(ctx, 1320, 760, tip, glow_a=0.6)
    P.ledge(ctx, 1220, 760, 260)
    hw = ease_in_out(ramp(t, 0.9, 1.4))
    hx, hy = lerp(1270, 1180, hw), lerp(560, 380, hw)
    ctx.save()
    ctx.translate(hx, hy)
    ctx.rotate(-1.2)
    P.glow(ctx, 0, 0, 160, C["sun"], 0.5 * (1 - 0.5 * hw))
    P.hand_icon(ctx, 0, 0, 110, a=0.9 - 0.4 * hw, col=C["sun"], line=C["gold"])
    ctx.restore()
    word_label(ctx, "A MIND", 1360, 820, t, t_m, size=34, col=C["gold"])


def _nothing_box(ctx, cx, cy, size, a=1.0):
    rounded_rect(ctx, cx - size / 2 - 18, cy - size / 2 - 18, size + 36, size + 36, 10)
    outline_fill(ctx, C["stone_shade"], a=a)
    ctx.rectangle(cx - size / 2, cy - size / 2, size, size)
    outline_fill(ctx, C["night_bg"], width=3, a=a)


@scene("P1-15a", gold=("nothing.", "pop"))
def p115a(ctx, t, s):
    cx, cy, sz = W / 2, 480, 480
    _nothing_box(ctx, cx, cy, sz)
    text(ctx, "NOTHING", cx, cy - sz / 2 - 50, 44, C["ink"], spacing=10, alpha=ramp(t, 0.1, 0.4))
    t_p = s.wt("tiny", 0.5)
    rnd = random.Random(8)
    for i in range(40):
        born = t_p + rnd.uniform(0, max(s.dur - t_p, 0.5))
        life = rnd.uniform(0.25, 0.6)
        k = (t - born) % 1.4
        if t >= born and k < life:
            a = math.sin(k / life * math.pi)
            x, y = cx + rnd.uniform(-0.42, 0.42) * sz, cy + rnd.uniform(-0.42, 0.42) * sz
            P.glow(ctx, x, y, 26, C["sun"], 0.8 * a)
            rgb(ctx, C["papyrus"], a)
            ctx.arc(x, y, 3, 0, 2 * math.pi)
            ctx.fill()


@scene("P1-15b", gold=("energy,", "laws", "something."))
def p115b(ctx, t, s):
    z = lerp(1.0, 1.22, ease_in_out(ramp(t, 0.1, 1.2)))
    cx, cy, sz = W / 2, 500, 480 * z
    _nothing_box(ctx, cx, cy, sz)
    ctx.save()
    ctx.rectangle(cx - sz / 2, cy - sz / 2, sz, sz)
    ctx.clip()
    t_e = s.wt("sea", 0.35)
    wa = ease_out(ramp(t, t_e, 1.0))
    for k in range(9):  # shimmering waves of energy
        yy = cy - sz / 2 + (k + 0.5) * sz / 9
        ctx.move_to(cx - sz / 2, yy)
        for x in range(int(cx - sz / 2), int(cx + sz / 2) + 8, 8):
            ctx.line_to(x, yy + 14 * math.sin(x * 0.02 + t * 3 + k) * wa)
        rgb(ctx, C["gold"] if k % 2 else C["sun"], 0.7 * wa)
        ctx.set_line_width(3)
        ctx.stroke()
    ctx.restore()
    word_label(ctx, "ENERGY", cx - sz / 2 - 170, cy - 40, t, s.wt("energy", 0.45), size=38)
    word_label(ctx, "LAWS", cx + sz / 2 + 140, cy + 40, t, s.wt("laws", 0.55), size=38)
    ty = cy - sz / 2 - 50
    text(ctx, "NOTHING", cx, ty, 44, C["ink"], spacing=10)
    t_x = s.wt("not", 0.7)
    xu = ramp(t, t_x, 0.35)
    if xu > 0:
        w = text_width(ctx, "NOTHING", 44, spacing=10)
        ctx.move_to(cx - w / 2 - 10, ty - 14)
        ctx.line_to(cx - w / 2 - 10 + (w + 20) * xu, ty - 18)
        rgb(ctx, C["terracotta"])
        ctx.set_line_width(7)
        ctx.stroke()
    t_s = s.wt("something", 0.85)
    k = ramp(t, t_s, 0.3)
    if k > 0:
        rounded_rect(ctx, cx - 250, cy - 60, 500, 110, 16)
        outline_fill(ctx, C["papyrus"], a=k)
        word_label(ctx, "SOMETHING", cx, cy + 18, t, t_s, size=56, col=C["gold"])


@scene("P1-17", gold=("first", "domino.", "works"))
def p117(ctx, t, s):
    _transition(ctx, t, s, done=0)


def _transition(ctx, t, s, done):
    """Frame `done` completes (tick, gold) and moves to its slot; the next frame slides in."""
    t_tick = s.at(0.15)
    t_move = s.at(0.45)
    t_in = s.wt("next" if done == 0 else "third", 0.6)
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
            st.update(x=lerp(W + 300, P.FRAME_SLOTS[k], u), fill=u, title=ramp(t, t_in + 0.5, 0.4), alpha=1.0 if u > 0 else 0)
        else:
            st.update(alpha=0.0)
        sts.append(st)
    P.triptych(ctx, sts)


# ================================================================ PART 2: the dials

DIALS = [("Gravity", 600), ("Atomic force", 960), ("Expansion rate", 1320)]
DIAL_Y, DIAL_R = 500, 150


@scene("P2-02", gold=("rule", "gravity", "atoms", "expanded"))
def p202(ctx, t, s):
    section_label(ctx, s, t, "Picture 2 · the dials")
    keys = ("gravity", "atoms", "expanded")
    for i, (name, cx) in enumerate(DIALS):
        sc = pop(t, 0.3 + i * 0.25, 0.4)
        if sc <= 0:
            continue
        t_s = s.wt(keys[i], 0.35 + i * 0.2)
        needle = lerp(math.radians(205), P.BAND_MID, back(ramp(t, t_s, 0.9), 1.2))
        ctx.save()
        ctx.translate(cx, DIAL_Y)
        ctx.scale(sc, sc)
        ctx.translate(-cx, -DIAL_Y)
        P.dial(ctx, cx, DIAL_Y, DIAL_R, needle)
        ctx.restore()
        text(ctx, name.upper(), cx, DIAL_Y + DIAL_R + 70, 26, C["ink"], spacing=6, alpha=ramp(t, 0.6 + i * 0.25, 0.3))


@scene("P2-03", gold=("narrow", "range."))
def p203(ctx, t, s):
    z = ease_in_out(ramp(t, 0.2, 1.4))
    zx, zy = 960, DIAL_Y - DIAL_R * 0.7
    ctx.save()
    ctx.translate(zx, zy)
    ctx.scale(1 + 1.8 * z, 1 + 1.8 * z)
    ctx.translate(-zx, -zy + z * 12)
    for name, cx in DIALS:
        P.dial(ctx, cx, DIAL_Y, DIAL_R, P.BAND_MID)
        text(ctx, name.upper(), cx, DIAL_Y + DIAL_R + 70, 26, C["ink"], spacing=6, alpha=1 - z)
    ctx.restore()
    t_w = s.wt("narrow", 0.65)
    text(ctx, "A HAIR'S WIDTH", W / 2, 200, 64, C["ink"], spacing=10, alpha=ramp(t, t_w, 0.4), scale=pop(t, t_w),
         shadow=True)


SMALL_DIALS = [(330, 300), (330, 520), (330, 740)]


def _dial_panel(ctx, t, s, nudge, galaxy_k, atom_k, labels):
    """Dials down the left; a window on the right shows a galaxy (top) and an atom (bottom)."""
    for i, (cx, cy) in enumerate(SMALL_DIALS):
        n = nudge[i]
        P.dial(ctx, cx, cy, 95, P.BAND_MID + n * 0.55, warn=abs(n))
        text(ctx, DIALS[i][0].upper(), cx + 170, cy + 10, 24, C["ink"], spacing=5, align="left")
    wx, wy, ww, wh = 900, 150, 820, 690
    rounded_rect(ctx, wx - 16, wy - 16, ww + 32, wh + 32, 14)
    outline_fill(ctx, C["bronze"])
    ctx.save()
    rounded_rect(ctx, wx, wy, ww, wh, 6)
    ctx.clip_preserve()
    rgb(ctx, C["night_bg"])
    ctx.fill()
    rnd = random.Random(4)
    for _ in range(90):
        rgb(ctx, C["night_text"], rnd.uniform(0.2, 0.6))
        ctx.arc(rnd.uniform(wx, wx + ww), rnd.uniform(wy, wy + wh), 1.2, 0, 2 * math.pi)
        ctx.fill()
    gx, gy = wx + ww / 2, wy + wh * 0.28
    P.galaxy(ctx, gx, gy, 150 * (1 - 0.95 * galaxy_k), rot=t * 0.4 + galaxy_k * 6, a=1 - 0.9 * galaxy_k, seed=2)
    P.atom(ctx, wx + ww / 2, wy + wh * 0.74, 120, t, a=1 - 0.6 * atom_k, spread=atom_k, seed=5)
    ctx.restore()
    for txt, (x, y), k, t0 in labels:
        word_label(ctx, txt, x, y, t, t0, size=44, col=C["terracotta"], a=k)


@scene("P2-04", gold=("no", "stars."))
def p204(ctx, t, s):
    t_n = s.wt("slightly", 0.3)
    n = ease_out(ramp(t, t_n, 0.5))
    g = ease_in_out(ramp(t, s.wt("no", 0.6) - 0.3, 1.0))
    _dial_panel(ctx, t, s, (n, 0, 0), g, 0.0,
                [("NO STARS", (1310, 300), 1.0, s.wt("stars", 0.7))])


@scene("P2-05", gold=("no", "life."))
def p205(ctx, t, s):
    t_n = s.wt("another", 0.15)
    n = ease_out(ramp(t, t_n, 0.5))
    a = ease_out(ramp(t, s.wt("atoms", 0.3), 1.0))
    _dial_panel(ctx, t, s, (1, n * -1, 0), 1.0, a,
                [("NO STARS", (1310, 300), 1.0, -1), ("NO LIFE", (1310, 800), 1.0, s.wt("life", 0.8))])


@scene("P2-06", captions=False)
def p206(ctx, t, s):
    b = ease_out(ramp(t, 0.2, 0.35))   # needles snap back
    r = ease_in_out(ramp(t, 0.5, max(s.dur - 0.8, 0.4)))
    _dial_panel(ctx, t, s, (1 - b, -(1 - b), 0), 1 - r, 1 - r,
                [("NO STARS", (1310, 300), 1 - b, -1), ("NO LIFE", (1310, 800), 1 - b, -1)])
    for i, (cx, cy) in enumerate(SMALL_DIALS[:2]):
        P.tick(ctx, cx + 100, cy - 80, 40, ramp(t, 0.6 + i * 0.2, 0.4))


def _carbon(ctx, t, cx, cy, s=1.0):
    P.atom(ctx, cx, cy, 190 * s, t, electrons=6, seed=6, orbit=C["ink"], nucleus=0.0)
    ctx.arc(cx, cy, 62 * s, 0, 2 * math.pi)
    outline_fill(ctx, C["terracotta"])
    text(ctx, "C", cx, cy + 24 * s, 76 * s, C["papyrus"])
    text(ctx, "CARBON", cx, cy + 250 * s, 30, C["ink"], spacing=8)


LADDER_X, LADDER_W, RUNGS = 1300, 260, 7
GAP_RUNG = 4


def _ladder(ctx, t, rung_lit, q=0.0):
    top, bot = 230, 790
    for xx in (LADDER_X, LADDER_X + LADDER_W):
        ctx.rectangle(xx - 9, top - 20, 18, bot - top + 40)
        outline_fill(ctx, C["bronze"])
    for k in range(RUNGS):
        y = bot - (k + 0.5) * (bot - top) / RUNGS
        if k == GAP_RUNG:
            if rung_lit > 0:
                P.glow(ctx, LADDER_X + LADDER_W / 2, y, 200, C["gold"], 0.6 * rung_lit)
                ctx.rectangle(LADDER_X, y - 9, LADDER_W, 18)
                outline_fill(ctx, C["gold"], a=rung_lit)
            ctx.rectangle(LADDER_X + 6, y - 9, LADDER_W - 12, 18)
            rgb(ctx, C["gold"], 0.9)
            ctx.set_line_width(3)
            ctx.set_dash([10, 8])
            ctx.stroke()
            ctx.set_dash([])
            if q > 0:
                P.glow(ctx, LADDER_X + LADDER_W + 80, y, 90, C["gold"], 0.5 * q * (0.7 + 0.3 * math.sin(t * 5)))
                P.question_mark(ctx, LADDER_X + LADDER_W + 80, y + 30, 90, C["terracotta"], a=q)
        else:
            ctx.rectangle(LADDER_X, y - 8, LADDER_W, 16)
            outline_fill(ctx, C["stone_lit"])
    text(ctx, "ENERGY LEVELS", LADDER_X + LADDER_W / 2, bot + 80, 28, C["ink"], spacing=6)
    return bot - (GAP_RUNG + 0.5) * (bot - top) / RUNGS


@scene("P2-06b", gold=("one", "specific", "energy", "level."))
def p206b(ctx, t, s):
    _carbon(ctx, t, 640, 480, pop(t, 0.1, 0.5))
    _ladder(ctx, t, 0.0, q=ramp(t, s.wt("specific", 0.5), 0.5))


@scene("P2-06c", gold=("found", "exactly", "life."))
def p206c(ctx, t, s):
    _carbon(ctx, t, 640, 480)
    t_f = s.wt("found", 0.25)
    y = _ladder(ctx, t, ease_out(ramp(t, t_f, 0.5)))
    P.tick(ctx, LADDER_X + LADDER_W + 80, y, 70, ramp(t, t_f + 0.4, 0.5))
    t_l = s.wt("life", 0.65) - 0.6
    for k, fn in enumerate((P.leaf, P.hand_icon, P.heart)):
        u = ease_out(ramp(t, t_l + k * 0.3, 0.8))
        if u <= 0:
            continue
        ang = math.radians(-150 + k * 60)
        x, yy = 640 + math.cos(ang) * 320 * u, 480 + math.sin(ang) * 300 * u
        ctx.move_to(640, 480)
        ctx.line_to(x, yy)
        rgb(ctx, C["gold"], 0.5 * u)
        ctx.set_line_width(3)
        ctx.set_dash([8, 8])
        ctx.stroke()
        ctx.set_dash([])
        if fn is P.hand_icon:
            fn(ctx, x, yy, 70 * u, a=u)
        else:
            fn(ctx, x, yy, 50 * u, a=u)


@scene("P2-07T", base="overlay", captions=False)
def p207t(ctx, t, s):
    P.verse_card(ctx, t, "“A superintellect has monkeyed with physics.”", "Fred Hoyle · 1981",
                 gold=("superintellect",), per_word=0.22)


@scene("P2-10", base="overlay", captions=False)
def p210(ctx, t, s):
    P.verse_card(ctx, t, "The heavens declare the glory of God; the skies proclaim the work of his hands.",
                 "Psalm 19:1 · NIV", gold=("glory", "god;"), per_word=min(0.2, s.dur * 0.6 / 15))


@scene("P2-10a", gold=("notice.",))
def p210a(ctx, t, s):
    P.dial(ctx, 760, 470, 220, P.BAND_MID + 0.02 * math.sin(t * 2))
    sh = ease_out(ramp(t, s.wt("if", 0.45), 0.4)) * (1 - ramp(t, s.dur - 0.5, 0.4))
    cast.seeker(ctx, 1260, 800, 380, view="front", shrug=sh)


ARCHERS = [(260 + i * (1400 / 24), 560 + (i % 2) * 10, 48, cast.CROWD_ROBES[i % 5]) for i in range(25)] + \
          [(290 + i * (1400 / 24), 590 + (i % 2) * 10, 54, cast.CROWD_ROBES[(i + 2) % 5]) for i in range(25)]
FIG_X, FIG_FY, FIG_H = 960, 850, 380


def _landing(i):
    rnd = random.Random(100 + i)
    side = -1 if i % 2 else 1
    return FIG_X + side * rnd.uniform(130, 720), rnd.uniform(680, 850), rnd.uniform(-0.5, 0.5)


def _arrow_stuck(ctx, x, y, lean, s=1.0, a=1.0):
    dx, dy = math.sin(lean) * 60 * s, -math.cos(lean) * 60 * s
    ctx.move_to(x, y)
    ctx.line_to(x + dx, y + dy)
    rgb(ctx, C["ink"], a)
    ctx.set_line_width(3.5 * s)
    ctx.stroke()
    for side in (-1, 1):  # fletching
        ctx.move_to(x + dx * 0.85, y + dy * 0.85)
        ctx.line_to(x + dx + side * 8 * s, y + dy - 4 * s)
        rgb(ctx, C["terracotta"], a)
        ctx.set_line_width(3 * s)
        ctx.stroke()


@scene("P2-10b", gold=("fifty", "archers", "misses."))
def p210b(ctx, t, s):
    t_draw = s.wt("fifty", 0.3)
    t_fire = s.wt("fire", 0.55)
    for x, fy, h, robe in ARCHERS:
        cast.archer(ctx, x, fy, h, robe=robe, draw=ease_out(ramp(t, t_draw, 0.6)) * (1 - ramp(t, t_fire, 0.08)),
                    alpha=ramp(t, 0.1, 0.5))
    for i, (x, fy, h, _) in enumerate(ARCHERS):  # arrows fly toward us, all missing
        u = ramp(t, t_fire + (i % 10) * 0.03, 0.7)
        if u <= 0:
            continue
        lx, ly, lean = _landing(i)
        if u < 1:
            sx, sy = x - 12, fy - h * 0.58
            px, py = lerp(sx, lx, u), lerp(sy, ly - 60, u) - 120 * math.sin(u * math.pi)
            sc = lerp(0.3, 1.0, u)
            ang = math.atan2(ly - sy, lx - sx)
            ctx.move_to(px, py)
            ctx.line_to(px - math.cos(ang) * 60 * sc, py - math.sin(ang) * 60 * sc)
            rgb(ctx, C["ink"])
            ctx.set_line_width(3.5 * sc)
            ctx.stroke()
        else:
            _arrow_stuck(ctx, lx, ly, lean)
    cast.seeker(ctx, FIG_X, FIG_FY, FIG_H, view="back")


@scene("P2-10c", gold=("why", "missed."))
def p210c(ctx, t, s):
    z = lerp(1.25, 1.0, ease_out(ramp(t, 0.0, 1.5)))
    ctx.save()
    ctx.translate(W / 2, 700)
    ctx.scale(z, z)
    ctx.translate(-W / 2, -700)
    for x, fy, h, robe in ARCHERS:
        cast.archer(ctx, x, fy, h, robe=robe, alpha=0.7)
    for i in range(len(ARCHERS)):
        _arrow_stuck(ctx, *_landing(i))
    turn_t = s.wt("why", 0.55) - 0.4
    view = "front" if t < turn_t else "back"
    squash = 1 - 0.25 * math.sin(math.pi * ramp(t, turn_t - 0.12, 0.24))
    ctx.save()
    ctx.translate(FIG_X, FIG_FY)
    ctx.scale(squash, 1)
    ctx.translate(-FIG_X, -FIG_FY)
    cast.seeker(ctx, FIG_X, FIG_FY, FIG_H, view=view)
    ctx.restore()
    ctx.restore()


BUBBLES = [(random.Random(i).uniform(330, 1590), random.Random(i + 50).uniform(230, 760),
            random.Random(i + 90).uniform(50, 120), ("indigo", "olive", "terracotta", "gold", "bronze")[i % 5])
           for i in range(13)]


def _bubbles(ctx, t, unseen=0.0, scale=1.0, cx=W / 2, cy=490, a=1.0):
    for i, (x, y, r, col) in enumerate(BUBBLES):
        x = cx + (x - W / 2) * scale + 10 * math.sin(t * 0.8 + i)
        y = cy + (y - 490) * scale + 8 * math.cos(t * 0.7 + i * 2)
        r *= scale
        fill = 1 - unseen
        if fill > 0:
            g = cairo.RadialGradient(x - r * 0.3, y - r * 0.3, r * 0.1, x, y, r)
            g.add_color_stop_rgba(0, *C["papyrus"], 0.8 * fill * a)
            g.add_color_stop_rgba(1, *C[col], 0.75 * fill * a)
            ctx.arc(x, y, r, 0, 2 * math.pi)
            ctx.set_source(g)
            ctx.fill()
        ctx.arc(x, y, r, 0, 2 * math.pi)
        rgb(ctx, C["ink"] if unseen > 0.5 else C[col], a)
        ctx.set_line_width(3)
        if unseen > 0:
            ctx.set_dash([6, 8])
        ctx.stroke()
        ctx.set_dash([])


@scene("P2-12", gold=("nobody", "seen"))
def p212(ctx, t, s):
    t_u = s.wt("nobody", 0.45)
    u = ease_in_out(ramp(t, t_u, 0.9))
    _bubbles(ctx, t, unseen=u)
    for i in (1, 6, 10):
        x, y, r, _ = BUBBLES[i]
        word_label(ctx, "UNSEEN", x + 10 * math.sin(t * 0.8 + i), y + 12, t, t_u + 0.6 + i * 0.05, size=28)


@scene("P2-13", gold=("unseen", "designer", "universes.", "believing"))
def p213(ctx, t, s):
    px, py = W / 2, 330
    t_l = s.wt("designer", 0.25)
    t_r = s.wt("countless", 0.45)
    wob = math.sin(t * 3) * math.exp(-max(t - t_r, 0) * 1.2) * 0.12 * (t > t_l)
    tilt = (0.18 * ramp(t, t_l, 0.4) - 0.18 * ramp(t, t_r, 0.6)) + wob
    ctx.rectangle(px - 14, py, 28, 470)       # post
    outline_fill(ctx, C["bronze"])
    ctx.rectangle(px - 120, py + 470, 240, 30)
    outline_fill(ctx, C["bronze"])
    arm = 480
    ends = []
    for side in (-1, 1):
        ends.append((px + side * arm * math.cos(tilt), py - side * arm * math.sin(tilt) * -1))
    ctx.move_to(*ends[0])
    ctx.line_to(*ends[1])
    rgb(ctx, C["ink"])
    ctx.set_line_width(16)
    ctx.stroke()
    ctx.move_to(*ends[0])
    ctx.line_to(*ends[1])
    rgb(ctx, C["bronze"])
    ctx.set_line_width(9)
    ctx.stroke()
    ctx.arc(px, py, 20, 0, 2 * math.pi)
    outline_fill(ctx, C["gold"])
    for k, (ex, ey) in enumerate(ends):
        bowl_y = ey + 230
        for dx in (-110, 110):
            ctx.move_to(ex, ey)
            ctx.line_to(ex + dx, bowl_y)
            rgb(ctx, C["ink"])
            ctx.set_line_width(2.5)
            ctx.stroke()
        ctx.move_to(ex - 140, bowl_y)
        ctx.curve_to(ex - 120, bowl_y + 60, ex + 120, bowl_y + 60, ex + 140, bowl_y)
        ctx.close_path()
        outline_fill(ctx, C["bronze_face"])
        if k == 0:
            a = ramp(t, t_l, 0.4)
            P.ellipse(ctx, ex, bowl_y - 60, 40, 55)
            rgb(ctx, C["ink"], a)
            ctx.set_line_width(3)
            ctx.set_dash([6, 7])
            ctx.stroke()
            ctx.set_dash([])
            P.question_mark(ctx, ex, bowl_y - 38, 70, C["ink"], a=a)
            text(ctx, "ONE UNSEEN DESIGNER", ex, bowl_y + 110, 26, C["ink"], spacing=5, alpha=a)
        else:
            a = ramp(t, t_r, 0.4)
            rnd = random.Random(9)
            for i in range(34):
                bx, by = ex + rnd.uniform(-115, 115), bowl_y - 12 - rnd.uniform(0, 110) * (1 - abs(rnd.uniform(-1, 1)) * 0.5)
                ctx.arc(bx, by, rnd.uniform(8, 18), 0, 2 * math.pi)
                rgb(ctx, C["ink"], a * 0.9)
                ctx.set_line_width(2)
                ctx.set_dash([4, 5])
                ctx.stroke()
                ctx.set_dash([])
            text(ctx, "COUNTLESS UNSEEN UNIVERSES", ex, bowl_y + 110, 26, C["ink"], spacing=5, alpha=a)


@scene("P2-15", gold=("dominoes.", "dials.", "personal?", "third"))
def p215(ctx, t, s):
    _transition(ctx, t, s, done=1)


# ================================================================ PART 3: the painting

PAINT = (360, 180, 1200, 640)   # x, y, w, h of the fresco panel


def _fresco_frame(ctx, x, y, w, h, a=1.0):
    rounded_rect(ctx, x - 26, y - 26, w + 52, h + 52, 8)
    outline_fill(ctx, C["bronze"], a=a)


@scene("P3-02", gold=("painter.",))
def p302(ctx, t, s):
    x, y, w, h = PAINT
    _fresco_frame(ctx, x, y, w, h)
    ctx.rectangle(x, y, w, h)
    outline_fill(ctx, C["limestone"], width=3)
    t_ok = s.wt("painting", 0.5)
    fade = 1 - ramp(t, t_ok - 0.3, 0.4)
    rnd = random.Random(21)
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    for i in range(26):  # spills that land as nothing
        t0 = 0.1 + i * (t_ok * 0.7 / 26)
        u = ease_out(ramp(t, t0, 0.25))
        if u <= 0 or fade <= 0:
            continue
        cx, cy, r = x + rnd.uniform(0.05, 0.95) * w, y + rnd.uniform(0.05, 0.95) * h, rnd.uniform(18, 60)
        col = C[("terracotta", "indigo", "olive", "gold", "bronze")[i % 5]]
        for k in range(6):
            ang = k * 1.05 + i
            P.ellipse(ctx, cx + math.cos(ang) * r * 0.7 * u, cy + math.sin(ang) * r * 0.5 * u, r * 0.35 * u, r * 0.3 * u)
            rgb(ctx, col, 0.85 * fade)
            ctx.fill()
        P.ellipse(ctx, cx, cy, r * u, r * 0.8 * u)
        rgb(ctx, col, 0.85 * fade)
        ctx.fill()
        ctx.rectangle(cx - 4, cy, 8, r * 1.6 * ramp(t, t0 + 0.2, 0.8))   # drip
        ctx.fill()
    ctx.restore()
    # then the painter's brush: a clean horizon, the painting reveals left to right
    rv = ease_in_out(ramp(t, t_ok, max(s.dur - t_ok - 0.3, 0.6)))
    if rv > 0:
        ctx.save()
        ctx.rectangle(x, y, w * rv, h)
        ctx.clip()
        P.sunrise(ctx, x, y, w, h)
        ctx.restore()
        bx, by = x + w * rv, y + h * 0.55
        ctx.save()
        ctx.translate(bx, by)
        ctx.rotate(0.6)
        ctx.rectangle(-6, -230, 12, 200)   # reed brush
        outline_fill(ctx, C["bronze"])
        ctx.move_to(-8, -30)
        ctx.curve_to(-10, -10, -2, 4, 0, 10)
        ctx.curve_to(2, 4, 10, -10, 8, -30)
        ctx.close_path()
        outline_fill(ctx, C["indigo"])
        ctx.restore()


def _painting_full(ctx, t, s, zoom=1.0, focus=(0.5, 0.5)):
    """The sunrise painting zoomed: 1.0 shows it framed; larger fills the screen around focus."""
    x, y, w, h = PAINT
    fx, fy = x + w * focus[0], y + h * focus[1]
    ctx.save()
    ctx.translate(W / 2, H / 2 - 40)
    ctx.scale(zoom, zoom)
    ctx.translate(-fx, -fy)
    _fresco_frame(ctx, x, y, w, h)
    P.sunrise(ctx, x, y, w, h)
    return x, y, w, h


@scene("P3-07", gold=("inside", "us."))
def p307(ctx, t, s):
    focus = (0.28, 0.82)
    z = lerp(1.0, 4.2, ease_in_out(ramp(t, 0.2, s.dur * 0.6)))
    x, y, w, h = _painting_full(ctx, t, s, z, focus)
    sx = x + w * focus[0]
    sy = P.shore_y(x, y, w, h, focus[0]) + 6
    cast.crowd_figure(ctx, sx, sy, 60, "indigo")
    g = ramp(t, s.wt("inside", 0.6), 0.6) * (0.75 + 0.25 * math.sin(t * 5))
    P.glow(ctx, sx, sy - 42, 30, C["sun"], 0.95 * g)
    P.glow(ctx, sx, sy - 42, 8, C["papyrus"], g)
    ctx.restore()


@scene("P3-06", base="overlay", captions=False)
def p306(ctx, t, s):
    P.verse_card(ctx, t, "For since the creation of the world God's invisible qualities, his eternal power and "
                 "divine nature, have been clearly seen, being understood from what has been made.",
                 "Romans 1:20 · NIV", gold=("eternal", "power", "divine", "nature,"), size=56, max_w=1180, pw=1400,
                 per_word=min(0.16, s.dur * 0.65 / 30))


@scene("P3-09", base="night", captions=False)
def p309(ctx, t, s):
    # Romans 2:15, written in light: gold words on a dark sheet, each glowing as it appears
    P.verse_card(ctx, t, "They show that the requirements of the law are written on their hearts, their "
                 "consciences also bearing witness.", "Romans 2:15 · NIV", gold=("written", "hearts,"),
                 glow_words=True, per_word=min(0.2, s.dur * 0.6 / 18), size=60)


@scene("P3-10", gold=("evolved,", "survived"))
def p310(ctx, t, s):
    grp = [(520 + dx, 720 + dy) for dx, dy in ((-120, 0), (-40, 20), (40, 0), (120, 20), (0, -40))]
    for i, (x, fy) in enumerate(grp):
        cast.crowd_figure(ctx, x, fy, 170, cast.CROWD_ROBES[i % 5], alpha=pop(t, 0.1 + i * 0.1, 0.4) and 1.0)
    rgb(ctx, C["gold"])                          # joined hands: cooperation
    ctx.set_line_width(6)
    for (x1, y1), (x2, y2) in zip(grp[:4], grp[1:4]):
        ctx.move_to(x1 + 22, y1 - 70)
        ctx.line_to(x2 - 22, y2 - 70)
        ctx.stroke()
    t_a = s.wt("survived", 0.6)
    u = ease_out(ramp(t, t_a, 0.8))
    if u > 0:
        ctx.move_to(720, 600)
        ctx.curve_to(900, 420, 1100, 360, lerp(720, 1300, u), lerp(600, 330, u))
        rgb(ctx, C["bronze"])
        ctx.set_line_width(8)
        ctx.stroke()
        P.arrow(ctx, 1240, 360, lerp(720, 1310, u), lerp(600, 325, u), C["bronze"], 8, 30, p=1.0)
        word_label(ctx, "SURVIVAL", 1380, 280, t, t_a + 0.5, size=42, col=C["olive"])
    for i in range(7):                           # the group that cooperates grows
        k = ramp(t, t_a + 0.8 + i * 0.12, 0.4)
        if k > 0:
            cast.crowd_figure(ctx, 1180 + (i % 4) * 90 + (i // 4) * 45, 760 + (i // 4) * 40, 130,
                              cast.CROWD_ROBES[(i + 1) % 5], alpha=k)


@scene("P3-11", gold=("evil.", "unpopular."))
def p311(ctx, t, s):
    t_e = s.wt("evil", 0.6)
    t_u = s.wt("unpopular", 0.85)
    ea = 1 - 0.75 * ramp(t, t_u - 0.3, 0.5)
    text(ctx, "EVIL", W / 2, 520, 200, C["terracotta"], spacing=24, alpha=ramp(t, t_e - 0.4, 0.4) * ea, shadow=True)
    ua = ramp(t, t_u, 0.4)
    if ua > 0:  # UNPOPULAR, set crooked and shaky: it looks wrong
        jig = math.sin(t * 23) * 3
        text(ctx, "UNPOPULAR", W / 2 + jig, 700, 110, C["ink"], spacing=10, alpha=ua, rot=-0.06 + 0.01 * math.sin(t * 9),
             scale=pop(t, t_u))
        P.question_mark(ctx, W / 2 + 470, 660, 90, C["terracotta"], a=ramp(t, t_u + 0.5, 0.4))


def _scroll(ctx, x, y, w, h, seed, gold_lines, t, t_g, title):
    for yy in (y - 18, y + h + 18):
        rounded_rect(ctx, x - 30, yy - 18, w + 60, 36, 18)
        outline_fill(ctx, C["bronze"])
    ctx.rectangle(x, y, w, h)
    outline_fill(ctx, C["papyrus"])
    text(ctx, title, x + w / 2, y - 70, 30, C["ink"], spacing=8)
    rnd = random.Random(seed)
    for i in range(8):
        ly = y + 50 + i * (h - 80) / 7
        if i in gold_lines:
            g = ramp(t, t_g + gold_lines.index(i) * 0.3, 0.5)
            P.glow(ctx, x + w / 2, ly - 10, w * 0.55, C["gold"], 0.35 * g)
            txt = ("Courage in battle", "Keep faith with your friends")[gold_lines.index(i)]
            text(ctx, txt, x + w / 2, ly, 32, mix_col(g), italic=True)
        else:
            xx = x + 40
            while xx < x + w - 50:  # unreadable script, different on each scroll
                seg = rnd.uniform(14, 46)
                ctx.move_to(xx, ly - 10 + rnd.uniform(-3, 3))
                ctx.line_to(xx + seg, ly - 10 + rnd.uniform(-3, 3))
                xx += seg + rnd.uniform(8, 16)
            rgb(ctx, C["ink"], 0.55)
            ctx.set_line_width(3)
            ctx.stroke()


def mix_col(g):
    from .core import mix
    return mix(C["ink"], C["gold"], g)


@scene("P3-12b", gold=("battle,", "betraying", "match."))
def p312b(ctx, t, s):
    t_g = s.wt("no", 0.4)
    _scroll(ctx, 330, 230, 560, 560, 1, [2, 5], t, t_g, "EGYPT")
    _scroll(ctx, 1030, 230, 560, 560, 2, [2, 5], t, t_g, "BABYLON")


@scene("P3-13", gold=("started", "dials.", "painter:"))
def p313(ctx, t, s):
    keys = (("started", 0.25), ("dials", 0.45), ("painter", 0.7))
    sts = []
    for k, (w, f) in enumerate(keys):
        t0 = s.wt(w, f)
        sts.append({"fill": 1.0, "title": 1.0, "lit": ease_out(ramp(t, t0, 0.4)), "tick": 1.0 if k < 2 else ramp(t, 0.3, 0.4)})
    P.triptych(ctx, sts)


# ================================================================ PART 4: the painter steps into the painting

@scene("P4-01", gold=("painter.",))
def p401(ctx, t, s):
    z = lerp(1.0, 1.55, ease_in_out(ramp(t, 0.2, s.dur - 0.3)))
    _painting_full(ctx, t, s, z)
    ctx.restore()


def _jesus_on_shore(ctx, t, x, y, w, h, fx, hgt, step=0.0, reach=0.0, a=1.0):
    sy = P.shore_y(x, y, w, h, fx) + 4
    cast.jesus(ctx, x + w * fx, sy, hgt, step=step, reach=reach, alpha=a)


@scene("P4-03", gold=("step", "into", "painting."))
def p403(ctx, t, s):
    x, y, w, h = _painting_full(ctx, t, s, 1.55)
    t_p = s.wt("step", 0.45)
    rv = ease_out(ramp(t, t_p - 0.3, 0.8))         # painted in by the brush
    walk = ramp(t, t_p + 0.5, s.dur)
    fx = lerp(0.2, 0.3, walk)
    hgt = lerp(150, 135, walk)
    if rv > 0:
        ctx.save()
        sy = P.shore_y(x, y, w, h, fx)
        ctx.rectangle(x + w * fx - 60, sy - hgt * rv - 10, 120, hgt * rv + 20)
        ctx.clip()
        _jesus_on_shore(ctx, t, x, y, w, h, fx, hgt, step=math.sin(t * 6) * (walk > 0), a=1.0)
        ctx.restore()
        if rv < 1:  # brush tip at the reveal line
            P.glow(ctx, x + w * fx, P.shore_y(x, y, w, h, fx) - hgt * rv, 30, C["gold"], 0.8)
    ctx.restore()


@scene("P4-04T", base="overlay", captions=False)
def p404t(ctx, t, s):
    P.verse_card(ctx, t, "In the beginning was the Word, and the Word was with God, and the Word was God.",
                 "John 1:1 · NIV", gold=("word,", "word", "god."), per_word=min(0.2, s.dur * 0.6 / 18))


@scene("P4-06aT", base="overlay", captions=False)
def p406at(ctx, t, s):
    P.verse_card(ctx, t, "Christus “suffered the extreme penalty … at the hands of … Pontius Pilatus.”",
                 "Tacitus · Annals 15.44 · c. AD 116", gold=("christus",), per_word=min(0.2, s.dur * 0.6 / 14))


@scene("P4-08T", base="overlay", captions=False)
def p408t(ctx, t, s):
    P.verse_card(ctx, t, "In the past God spoke to our ancestors through the prophets at many times and in various "
                 "ways, but in these last days he has spoken to us by his Son.", "Hebrews 1:1-2 · NIV",
                 gold=("son.",), size=58, pw=1400, max_w=1180, per_word=min(0.16, s.dur * 0.65 / 29))


@scene("P4-14", base="overlay", captions=False)
def p414(ctx, t, s):
    P.verse_card(ctx, t, "You will seek me and find me when you seek me with all your heart.", "Jeremiah 29:13 · NIV",
                 gold=("find", "heart."), per_word=min(0.22, s.dur * 0.6 / 14))


@scene("P4-15", gold=("started", "designed", "personal."))
def p415(ctx, t, s):
    keys = (("dominoes", 0.1), ("dials", 0.4), ("painting", 0.72))
    sts = []
    for k, (w, f) in enumerate(keys):
        t0 = s.wt(w, f)
        sts.append({"fill": 1.0, "title": 1.0, "lit": ease_out(ramp(t, t0, 0.4)),
                    "scale": 1 + 0.08 * math.exp(-max(t - t0, 0) * 3) * (t >= t0)})
    P.triptych(ctx, sts)


@scene("P4-16", gold=("looking", "you."))
def p416(ctx, t, s):
    # He stops on the shore with the sun rising ahead, and holds an open hand back toward the
    # viewer. Still seen from behind (system prompt 5.2): an invitation, not a face.
    z = lerp(1.55, 2.6, ease_in_out(ramp(t, 0.0, s.dur)))
    x, y, w, h = _painting_full(ctx, t, s, z, focus=(0.32, 0.72))
    P.glow(ctx, x + w * 0.5, y + h * 0.5, w * 0.6, C["sun"], 0.3 * ramp(t, 0.3, s.dur))
    reach = ease_in_out(ramp(t, s.wt("looking", 0.5) - 0.3, 0.9))
    _jesus_on_shore(ctx, t, x, y, w, h, 0.32, 135, reach=reach)
    ctx.restore()


# ================================================================ OUTRO

@scene("O-02", gold=("send", "someone"))
def o02(ctx, t, s):
    # a carrier pigeon takes a small sealed scroll and flies off with it
    u = ease_in_out(ramp(t, s.at(0.3), s.dur * 0.65))
    x, y = lerp(W / 2, W + 200, u), lerp(560, 120, u) - 60 * math.sin(u * math.pi)
    sc = lerp(1.0, 0.55, u)
    if u <= 0:
        x, y = W / 2, 560 + 6 * math.sin(t * 3)
    flap = math.sin(t * (14 if u > 0 else 3))
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(sc, sc)
    ctx.rotate(-0.25 * (u > 0))
    for side in (-1,):   # far wing
        ctx.move_to(-10, -10)
        ctx.curve_to(-40, -90 * flap - 20, 40, -110 * flap - 20, 60, -20)
        ctx.close_path()
        outline_fill(ctx, C["seeker_robe_shade"])
    P.ellipse(ctx, 0, 0, 90, 45)                 # body
    outline_fill(ctx, C["seeker_robe"])
    ctx.arc(80, -30, 30, 0, 2 * math.pi)         # head
    outline_fill(ctx, C["seeker_robe"])
    ctx.move_to(106, -32)
    ctx.line_to(130, -24)
    ctx.line_to(106, -20)
    ctx.close_path()
    outline_fill(ctx, C["gold"], width=3)
    ctx.arc(88, -36, 4, 0, 2 * math.pi)
    rgb(ctx, C["ink"])
    ctx.fill()
    ctx.move_to(-80, -10)                        # tail
    ctx.line_to(-150, -30)
    ctx.line_to(-150, 20)
    ctx.close_path()
    outline_fill(ctx, C["seeker_robe_shade"])
    rounded_rect(ctx, -20, 30, 50, 22, 10)       # the scroll tied to its leg
    outline_fill(ctx, C["papyrus"], width=3)
    ctx.rectangle(0, 28, 6, 26)
    rgb(ctx, C["terracotta"])
    ctx.fill()
    ctx.move_to(-10, -6)                         # near wing
    ctx.curve_to(-50, 80 * flap - 10, 30, 100 * flap - 10, 60, 0)
    ctx.close_path()
    outline_fill(ctx, C["papyrus_dark"])
    ctx.restore()


# ---------------------------------------------------------------- preview

def preview_lines() -> dict:
    """shot id -> (full spoken line, estimated seconds) from the script, for previews."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from episodes.ep001.shots import SHOTS
    from jta_agent.pipeline import PREFIX_PART
    from jta_agent.voice import parse_script, row_key
    lines = {(l.part, l.row): l.text for l in parse_script(Path(__file__).resolve().parents[1] / "episodes/ep001/script.md")}
    out = {}
    for sh in SHOTS:
        if sh.id not in REG:
            continue
        pre, row = sh.id.split("-", 1)
        txt = lines.get((PREFIX_PART[pre], row_key(row)), "")
        if REG[sh.id].base == "overlay" or txt.startswith("("):
            txt = txt if not txt.startswith("(") else ""
        dur = max(3.5, len(txt.split()) * 0.36 + 0.8) if txt else 3.0
        out[sh.id] = (txt, dur)
    return out


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "anim_out")
    pl = preview_lines()
    ids = sys.argv[2:] or list(pl)
    for i in ids:
        txt, dur = pl[i]
        render_shot(i, dur, out / f"{i}.mp4", line=txt)
        print("wrote", i)
