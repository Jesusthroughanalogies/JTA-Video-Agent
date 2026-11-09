"""A small renderer for new JTA Shorts in the series' look (1080x1920, 30 fps).

The look: dusk skies, dark silhouettes, warm sun glow, gold-highlighted serif captions near the
top third, scripture labels at the bottom, Greek word cards. Every reel is a script of beats;
captions are timed per word. Until a voiceover exists, word times are estimated from a steady
narration pace. Once Paul's voice is recorded and aligned, `Reel.apply_alignment()` swaps in
the real word times and the same scenes re-render in sync, with nothing redrawn by hand.
"""
from __future__ import annotations

import json
import math
import random
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cairo
import numpy as np

W, H, FPS = 1080, 1920, 30
SERIF = "IM FELL DW Pica"
GREEK = "DejaVu Serif"


def hx(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


C = {k: hx(v) for k, v in {
    "gold": "#E8B04B", "gold_soft": "#F2CF86", "white": "#F4EFE6", "ink": "#08070D", "sil": "#0B0A12",
    "red": "#B5332E", "paper": "#EDE4CF", "paper_line": "#B9AE95", "shirt": "#EFEAE0",
    "sun": "#FFE6A8",
}.items()}

SKIES = {   # top -> bottom stops
    "dusk": [(0.0, "#16142E"), (0.42, "#4A3463"), (0.62, "#9A5468"), (0.74, "#E59A5C")],
    "night": [(0.0, "#06070F"), (0.6, "#121429"), (1.0, "#1D1B33")],
    "dawn": [(0.0, "#22365F"), (0.45, "#5E6F9C"), (0.66, "#D9A47A"), (0.76, "#F5CB86")],
    "dark": [(0.0, "#07070C"), (1.0, "#0E0C16")],
}


# ---------------------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ramp(t, t0, d):
    return clamp((t - t0) / d) if d > 0 else float(t >= t0)


def ease(u):
    u = clamp(u)
    return u * u * (3 - 2 * u)


def ease_out(u):
    u = clamp(u)
    return 1 - (1 - u) ** 3


def lerp(a, b, u):
    return a + (b - a) * u


def rgb(ctx, col, a=1.0):
    ctx.set_source_rgba(col[0], col[1], col[2], a)


# ---------------------------------------------------------------------------- backdrops
def sky(ctx, preset: str, mix_to: Optional[str] = None, k: float = 0.0, horizon: float = 1.0):
    def grad(stops):
        g = cairo.LinearGradient(0, 0, 0, H * horizon)
        for p, c in stops:
            g.add_color_stop_rgb(p, *hx(c))
        return g
    ctx.rectangle(0, 0, W, H)
    ctx.set_source(grad(SKIES[preset]))
    ctx.fill()
    if mix_to and k > 0:
        ctx.rectangle(0, 0, W, H)
        ctx.set_source(grad(SKIES[mix_to]))
        ctx.paint_with_alpha(k)


_STARS = [(random.Random(i).random() * W, random.Random(i + 999).random() * H * 0.55,
           random.Random(i + 77).random()) for i in range(140)]


def stars(ctx, t, a=1.0):
    for x, y, s in _STARS:
        tw = 0.55 + 0.45 * math.sin(t * (1.2 + s) + s * 20)
        rgb(ctx, C["white"], a * tw * (0.25 + 0.5 * s))
        ctx.arc(x, y, 0.8 + 1.6 * s, 0, math.tau)
        ctx.fill()


def glow(ctx, x, y, r, col, a):
    if a <= 0:
        return
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, col[0], col[1], col[2], a)
    g.add_color_stop_rgba(0.45, col[0], col[1], col[2], a * 0.35)
    g.add_color_stop_rgba(1, col[0], col[1], col[2], 0)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, math.tau)
    ctx.fill()


def sun(ctx, x, y, r, a=1.0):
    glow(ctx, x, y, r * 6, C["sun"], 0.35 * a)
    glow(ctx, x, y, r * 2.2, C["sun"], 0.6 * a)
    rgb(ctx, hx("#FFF3D6"), a)
    ctx.arc(x, y, r, 0, math.tau)
    ctx.fill()


def rays(ctx, x, y, a, rot=0.0, n=18, length=1600):
    if a <= 0:
        return
    for i in range(n):
        ang = rot + i * math.tau / n
        w = 0.05
        ctx.move_to(x, y)
        ctx.line_to(x + math.cos(ang - w) * length, y + math.sin(ang - w) * length)
        ctx.line_to(x + math.cos(ang + w) * length, y + math.sin(ang + w) * length)
        ctx.close_path()
        g = cairo.RadialGradient(x, y, 0, x, y, length)
        g.add_color_stop_rgba(0, 1, 0.93, 0.75, 0.16 * a)
        g.add_color_stop_rgba(1, 1, 0.93, 0.75, 0)
        ctx.set_source(g)
        ctx.fill()


def hill(ctx, base, amp, freq, phase, col, a=1.0):
    ctx.move_to(0, H)
    for x in range(0, W + 21, 20):
        ctx.line_to(x, base - amp * math.sin(x / W * math.tau * freq + phase) - amp * 0.4 * math.sin(x / W * 17 + phase))
    ctx.line_to(W, H)
    ctx.close_path()
    rgb(ctx, hx(col) if isinstance(col, str) else col, a)
    ctx.fill()


def hill_y(x, base, amp, freq, phase):
    return base - amp * math.sin(x / W * math.tau * freq + phase) - amp * 0.4 * math.sin(x / W * 17 + phase)


def grass(ctx, base, amp, freq, phase, col, sway=0.0, density=9):
    rnd = random.Random(int(base))
    rgb(ctx, hx(col) if isinstance(col, str) else col)
    ctx.set_line_width(2)
    for x in range(0, W, density):
        y = hill_y(x, base, amp, freq, phase)
        h = 10 + rnd.random() * 16
        ctx.move_to(x, y + 2)
        ctx.line_to(x + sway * h * 0.8 + rnd.uniform(-2, 2), y - h)
        ctx.stroke()


# ---------------------------------------------------------------------------- figures
def person(ctx, x, fy, h, *, step=0.0, lean=0.0, arm_l=-0.15, arm_r=0.15, look_up=0.0, a=1.0,
           rim: float = 0.0, col=None):
    """A silhouette in a robe, feet at (x, fy). step -1..1 swings the legs; arms are angles from straight down
    (radians, positive = forward/right). rim adds a soft gold edge glow."""
    col = col or C["sil"]
    u = h / 100
    ctx.save()
    ctx.translate(x, fy)
    ctx.rotate(lean * 0.25)
    if rim:
        glow(ctx, 0, -55 * u, 60 * u, C["gold"], 0.25 * rim)
    ctx.push_group()
    rgb(ctx, col)
    # legs
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(7 * u)
    for s in (step, -step):
        ctx.move_to(0, -26 * u)
        ctx.line_to(s * 14 * u, -2 * u)
        ctx.stroke()
    # robe
    ctx.move_to(-10 * u, -72 * u)
    ctx.curve_to(-13 * u, -55 * u, -16 * u, -35 * u, -15 * u - step * 3 * u, -20 * u)
    ctx.line_to(15 * u + step * 3 * u, -20 * u)
    ctx.curve_to(16 * u, -35 * u, 13 * u, -55 * u, 10 * u, -72 * u)
    ctx.curve_to(5 * u, -76 * u, -5 * u, -76 * u, -10 * u, -72 * u)
    ctx.fill()
    # arms
    ctx.set_line_width(5.5 * u)
    for side, ang in ((-1, arm_l), (1, arm_r)):
        sx, sy = side * 8 * u, -70 * u
        ex = sx + math.sin(ang) * 30 * u
        ey = sy + math.cos(ang) * 30 * u
        ctx.move_to(sx, sy)
        ctx.line_to(ex, ey)
        ctx.stroke()
    # head
    ctx.arc(1.5 * u * look_up, -84 * u - 1.5 * u * look_up, 8.5 * u, 0, math.tau)
    ctx.fill()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()


def hand_pos(x, fy, h, arm, side=1, lean=0.0):
    u = h / 100
    sx, sy = side * 8 * u, -70 * u
    ex, ey = sx + math.sin(arm) * 30 * u, sy + math.cos(arm) * 30 * u
    c, s = math.cos(lean * 0.25), math.sin(lean * 0.25)
    return x + ex * c - ey * s, fy + ex * s + ey * c


# ---------------------------------------------------------------------------- text
def font(ctx, size, italic=False, face=SERIF):
    ctx.select_font_face(face, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)


def text(ctx, s, x, y, size, col=C["white"], a=1.0, italic=False, align="center", face=SERIF, spacing=0.0):
    font(ctx, size, italic, face)
    if spacing:
        ws = [ctx.text_extents(ch).x_advance for ch in s]
        tw = sum(ws) + spacing * (len(s) - 1)
    else:
        tw = ctx.text_extents(s).x_advance
    x0 = x - tw / 2 if align == "center" else (x - tw if align == "right" else x)
    rgb(ctx, col, a)
    if spacing:
        cx = x0
        for ch, w in zip(s, ws):
            ctx.move_to(cx, y)
            ctx.show_text(ch)
            cx += w + spacing
    else:
        ctx.move_to(x0, y)
        ctx.show_text(s)
    return tw


def wavy(ctx, x0, x1, y, col, a, p=1.0):
    if a <= 0 or p <= 0:
        return
    xe = x0 + (x1 - x0) * p
    ctx.move_to(x0, y)
    x = x0
    while x < xe:
        x = min(x + 4, xe)
        ctx.line_to(x, y + 2.5 * math.sin((x - x0) / 9))
    rgb(ctx, col, a)
    ctx.set_line_width(2.4)
    ctx.stroke()


def label(ctx, ref, quote, t, t0, y=1700, a=1.0):
    """Scripture label: small-caps reference over a gold rule with diamonds, the KJV words in italics."""
    k = ease(ramp(t, t0, 0.5)) * a
    if k <= 0:
        return
    text(ctx, ref.upper(), W / 2, y, 30, C["white"], 0.9 * k, spacing=5)
    w = 300 * ease_out(ramp(t, t0 + 0.15, 0.6))
    rgb(ctx, C["gold"], 0.8 * k)
    ctx.set_line_width(1.6)
    ctx.move_to(W / 2 - w / 2, y + 18)
    ctx.line_to(W / 2 + w / 2, y + 18)
    ctx.stroke()
    for dx in (-w / 2, w / 2):
        ctx.save()
        ctx.translate(W / 2 + dx, y + 18)
        ctx.rotate(math.pi / 4)
        ctx.rectangle(-4, -4, 8, 8)
        ctx.restore()
        ctx.fill()
    if quote:
        text(ctx, f"“{quote}”", W / 2, y + 70, 36, C["white"], 0.8 * ease(ramp(t, t0 + 0.4, 0.6)) * a,
             italic=True)


def hook_card(ctx, lines, t, t_end, gold_line=1):
    """Opening title, the series' way: centred caps, the key line big and gold."""
    k = ease(ramp(t, 0.05, 0.35)) * (1 - ease(ramp(t, t_end - 0.3, 0.3)))
    if k <= 0:
        return
    sizes = [52, 104, 44]
    ys = [560, 690, 770]
    for i, ln in enumerate(lines):
        big = i == gold_line
        text(ctx, ln, W / 2, ys[i], sizes[i] if not big else _fit(ctx, ln, sizes[i], 960, 3),
             C["gold"] if big else C["white"], k * ease(ramp(t, 0.1 + i * 0.25, 0.4)),
             italic=(i == 2), spacing=3 if i < 2 else 0)


def _fit(ctx, s, size, max_w, spacing):
    while size > 40:
        font(ctx, size)
        if sum(ctx.text_extents(ch).x_advance for ch in s) + spacing * len(s) <= max_w:
            break
        size -= 4
    return size


def greek_card(ctx, t, t0, word, translit, gloss, y=980):
    k = ease(ramp(t, t0, 0.6))
    if k <= 0:
        return
    glow(ctx, W / 2, y - 40, 420, C["gold"], 0.22 * k)
    text(ctx, word, W / 2, y, 150, C["gold"], k, face=GREEK)
    text(ctx, translit, W / 2, y + 84, 42, C["white"], 0.75 * k, italic=True)
    text(ctx, gloss.upper(), W / 2, y + 150, 22, C["white"], 0.7 * k * ease(ramp(t, t0 + 0.5, 0.5)), spacing=4)
    w = 380 * ease_out(ramp(t, t0 + 0.6, 0.7))
    rgb(ctx, C["gold"], 0.75 * k)
    ctx.set_line_width(1.5)
    ctx.move_to(W / 2 - w / 2, y + 168)
    ctx.line_to(W / 2 + w / 2, y + 168)
    ctx.stroke()


def tag(ctx, s, x, y, t, t0, strike_at=None, rot=-0.04):
    """A small paper tag with an italic word, optionally struck through later."""
    k = ease_out(ramp(t, t0, 0.35))
    if k <= 0:
        return
    ctx.save()
    ctx.translate(x, y + (1 - k) * 20)
    ctx.rotate(rot)
    font(ctx, 44, italic=True)
    tw = ctx.text_extents(s).x_advance
    ctx.rectangle(-tw / 2 - 20, -48, tw + 40, 68)
    rgb(ctx, C["paper"], 0.95 * k)
    ctx.fill()
    text(ctx, s, 0, 0, 44, hx("#3A2E22"), k, italic=True)
    if strike_at is not None:
        p = ease_out(ramp(t, strike_at, 0.35))
        if p > 0:
            ctx.move_to(-tw / 2 - 8, -10)
            ctx.line_to(-tw / 2 - 8 + (tw + 16) * p, -14)
            rgb(ctx, C["red"], 0.9 * k)
            ctx.set_line_width(4)
            ctx.stroke()
    ctx.restore()


# ---------------------------------------------------------------------------- script timing
@dataclass
class Beat:
    id: str
    text: str
    gold: tuple = ()
    caption: bool = True          # hook beats are shown by the hook card instead
    hold: float = 0.0             # extra seconds after the beat (a visual moment)


@dataclass
class Word:
    w: str
    t0: float
    t1: float
    beat: str
    gold: bool


@dataclass
class Reel:
    slug: str
    title: str
    beats: list[Beat]
    draw: Callable[["Reel", cairo.Context, float], None]
    hook_lines: tuple = ()
    words: list[Word] = field(default_factory=list)
    beat_t: dict = field(default_factory=dict)
    total: float = 0.0

    def script(self) -> str:
        return " ".join(b.text for b in self.beats)

    def time_estimate(self, wps_scale: float = 1.0, start: float = 0.35):
        """A steady narrator pace (~2.6 words/s) with pauses at punctuation."""
        t, self.words, self.beat_t = start, [], {}
        for b in self.beats:
            b0 = t
            for w in b.text.split():
                d = (0.26 + 0.03 * len(re.sub(r"\W", "", w))) * wps_scale
                core = re.sub(r"[^\w']", "", w).lower()
                self.words.append(Word(w, t, t + d, b.id, core in {g.lower() for g in b.gold}))
                t += d
                if w[-1] in ".?!":
                    t += 0.42
                elif w[-1] in ",;:":
                    t += 0.18
            t += 0.12 + b.hold
            self.beat_t[b.id] = (b0, t)
        self.total = t + 0.8
        return self

    def apply_alignment(self, path: Path):
        """Real word times from a transcript of the recorded voice: [{"word","start","end"}, ...] in order."""
        al = json.loads(Path(path).read_text())
        if len(al) != len(self.words):
            raise ValueError(f"alignment has {len(al)} words, script has {len(self.words)}")
        for w, a in zip(self.words, al):
            w.t0, w.t1 = float(a["start"]), float(a["end"])
        for b in self.beats:
            ws = [w for w in self.words if w.beat == b.id]
            self.beat_t[b.id] = (ws[0].t0, ws[-1].t1 + 0.12 + b.hold)
        self.total = self.words[-1].t1 + 0.8
        return self

    def B(self, beat_id: str) -> float:
        return self.beat_t[beat_id][0]

    def BE(self, beat_id: str) -> float:
        return self.beat_t[beat_id][1]

    def in_beat(self, t, first: str, last: Optional[str] = None) -> bool:
        return self.B(first) <= t < self.BE(last or first)


# ---------------------------------------------------------------------------- captions
def phrases(words: list[Word], max_words=6):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w.w[-1] in ".?!":
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def captions(ctx, reel: Reel, t, y=560, size=62, max_w=840):
    caps = [w for w in reel.words if next(b for b in reel.beats if b.id == w.beat).caption]
    ph = phrases(caps)
    for i, p in enumerate(ph):
        start = p[0].t0 - 0.15
        end = (ph[i + 1][0].t0 - 0.12) if i + 1 < len(ph) else p[-1].t1 + 1.2
        if not (start <= t < end):
            continue
        k = ease(ramp(t, start, 0.18)) * (1 - ease(ramp(t, end - 0.15, 0.15)))
        font(ctx, size)
        space = ctx.text_extents(" ").x_advance
        lines, cur, cw = [], [], 0.0
        for w in p:
            ww = ctx.text_extents(w.w).x_advance
            if cur and cw + space + ww > max_w:
                lines.append((cur, cw))
                cur, cw = [], 0.0
            cur.append((w, ww))
            cw += (space if cw else 0) + ww
        lines.append((cur, cw))
        lh = size * 1.22
        top = y - lh * (len(lines) - 1) / 2
        for li, (ln, lw) in enumerate(lines):
            x = W / 2 - lw / 2
            yy = top + li * lh
            for w, ww in ln:
                said = ramp(t, w.t0, 0.12)
                col = C["gold"] if w.gold else C["white"]
                a = k * (0.38 + 0.62 * said)
                rgb(ctx, C["ink"], 0.45 * a)
                ctx.move_to(x + 2, yy + 3)
                font(ctx, size)
                ctx.show_text(w.w)
                text(ctx, w.w, x, yy, size, col, a, align="left")
                if w.gold:
                    wavy(ctx, x, x + ww, yy + 12, C["gold"], a, ease_out(ramp(t, w.t0 + 0.05, 0.4)))
                x += ww + space
        return


# ---------------------------------------------------------------------------- finish + output
_GRAIN = None
_GRAIN_BUF = None


def finish(ctx, frame):
    global _GRAIN, _GRAIN_BUF
    if _GRAIN is None:
        n = 512
        a = (np.random.default_rng(3).random((n, n)) * 255).astype(np.uint8)
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A8, n)
        buf = np.zeros((n, stride), np.uint8)
        buf[:, :n] = a
        _GRAIN = cairo.ImageSurface.create_for_data(memoryview(buf), cairo.FORMAT_A8, n, n, stride)
        _GRAIN_BUF = buf
    pat = cairo.SurfacePattern(_GRAIN)
    pat.set_extend(cairo.EXTEND_REPEAT)
    m = cairo.Matrix()
    m.translate((frame * 137) % 512, (frame * 251) % 512)
    pat.set_matrix(m)
    ctx.set_source_rgba(1, 1, 1, 0.035)
    ctx.mask(pat)
    g = cairo.RadialGradient(W / 2, H * 0.48, H * 0.3, W / 2, H * 0.48, H * 0.78)
    g.add_color_stop_rgba(0, 0, 0, 0, 0)
    g.add_color_stop_rgba(1, 0, 0, 0, 0.42)
    ctx.set_source(g)
    ctx.paint()


def frame(reel: Reel, ctx, t, i):
    reel.draw(reel, ctx, t)
    captions(ctx, reel, t)
    if reel.hook_lines:
        hook_card(ctx, reel.hook_lines, t, reel.BE(reel.beats[0].id))
    fade_in, fade_out = ease(ramp(t, 0, 0.25)), 1 - ease(ramp(t, reel.total - 0.5, 0.5))
    if fade_in * fade_out < 1:
        ctx.set_source_rgba(0, 0, 0, 1 - fade_in * fade_out)
        ctx.paint()
    finish(ctx, i)


def still(reel: Reel, t: float, out: Path) -> Path:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(s)
    frame(reel, ctx, t, int(t * FPS))
    s.write_to_png(str(out))
    return out


def render(reel: Reel, out: Path, audio: Optional[Path] = None) -> Path:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(s)
    n = int(round(reel.total * FPS))
    a_in = ["-i", str(audio)] if audio else ["-f", "lavfi", "-t", f"{reel.total:.2f}", "-i",
                                               "anullsrc=channel_layout=stereo:sample_rate=48000"]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", *a_in, "-map", "0:v", "-map", "1:a", "-shortest",
                          "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "19",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
                         stdin=subprocess.PIPE)
    for i in range(n):
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgb(0, 0, 0)
        ctx.paint()
        ctx.restore()
        frame(reel, ctx, i / FPS, i)
        s.flush()
        p.stdin.write(bytes(s.get_data()))
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out
