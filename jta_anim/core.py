"""Drawing and rendering core: easing, kinetic type, labels, captions, grain, MP4 output."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Optional

import cairo
import numpy as np

from .theme import C, CAPTION_MAX_W, CAPTION_Y, FONT, FPS, GRAIN_ALPHA, H, OUTLINE, W

# ---------------------------------------------------------------- easing


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ramp(t: float, t0: float, dur: float) -> float:
    """0 before t0, 1 after t0+dur, linear between."""
    return clamp((t - t0) / dur) if dur > 0 else float(t >= t0)


def ease_out(u: float) -> float:
    u = clamp(u)
    return 1 - (1 - u) ** 3


def ease_in_out(u: float) -> float:
    u = clamp(u)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def back(u: float, s: float = 1.70158) -> float:
    """Overshoot pop, as in the reels."""
    u = clamp(u) - 1
    return u * u * ((s + 1) * u + s) + 1


def pop(t: float, t0: float, dur: float = 0.35) -> float:
    return back(ramp(t, t0, dur))


# ---------------------------------------------------------------- colour helpers


def rgb(ctx: cairo.Context, col, a: float = 1.0) -> None:
    ctx.set_source_rgba(col[0], col[1], col[2], a)


def mix(c1, c2, t: float):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- shapes


def outline_fill(ctx: cairo.Context, fill, line=C["ink"], width: float = OUTLINE, a: float = 1.0) -> None:
    rgb(ctx, fill, a)
    ctx.fill_preserve()
    rgb(ctx, line, a)
    ctx.set_line_width(width)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.stroke()


def rounded_rect(ctx: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def diamond(ctx: cairo.Context, x: float, y: float, s: float, col, a: float = 1.0) -> None:
    ctx.move_to(x, y - s)
    ctx.line_to(x + s, y)
    ctx.line_to(x, y + s)
    ctx.line_to(x - s, y)
    ctx.close_path()
    rgb(ctx, col, a)
    ctx.fill()


# ---------------------------------------------------------------- type


def font(ctx: cairo.Context, size: float, italic: bool = False) -> None:
    ctx.select_font_face(FONT, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)


def text_width(ctx: cairo.Context, s: str, size: float, italic: bool = False, spacing: float = 0) -> float:
    font(ctx, size, italic)
    if spacing:
        return sum(ctx.text_extents(ch).x_advance for ch in s) + spacing * (len(s) - 1)
    return ctx.text_extents(s).x_advance


def text(ctx: cairo.Context, s: str, x: float, y: float, size: float, col=C["ink"], *, align: str = "center",
         italic: bool = False, spacing: float = 0, alpha: float = 1.0, scale: float = 1.0,
         rot: float = 0.0, shadow: bool = False) -> float:
    """Draw text with its baseline at y. Returns the drawn width. scale pops around the text centre."""
    if alpha <= 0 or scale <= 0:
        return 0.0
    w = text_width(ctx, s, size, italic, spacing)
    ox = {"center": -w / 2, "left": 0, "right": -w}[align]
    ctx.save()
    ctx.translate(x + ox + w / 2, y - size * 0.32)
    ctx.rotate(rot)
    ctx.scale(scale, scale)
    ctx.translate(-w / 2, size * 0.32)
    font(ctx, size, italic)
    passes = [((0.0, 0.0), col, alpha)]
    if shadow:
        passes.insert(0, ((3.0, 4.0), C["ink"], alpha * 0.25))
    for (dx, dy), c, a in passes:
        rgb(ctx, c, a)
        if spacing:
            cx = dx
            for ch in s:
                ctx.move_to(cx, dy)
                ctx.show_text(ch)
                cx += ctx.text_extents(ch).x_advance + spacing
        else:
            ctx.move_to(dx, dy)
            ctx.show_text(s)
    ctx.new_path()  # show_text leaves a current point; clear it so the next arc does not join to it
    ctx.restore()
    return w


def label(ctx: cairo.Context, s: str, x: float, y: float, size: float = 30, *, alpha: float = 1.0,
          grow: float = 1.0, col=C["ink"]) -> None:
    """Letterspaced Fell caps with a gold rule and a diamond each side (the reels' label style).
    grow (0..1) draws the rules out from the text."""
    s = s.upper()
    w = text(ctx, s, x, y, size, col, spacing=size * 0.22, alpha=alpha)
    gap, rule = size * 0.7, size * 3.2 * clamp(grow)
    cy = y - size * 0.33
    ctx.set_line_width(2.2)
    rgb(ctx, C["gold"], alpha)
    for sign in (-1, 1):
        x0 = x + sign * (w / 2 + gap)
        if rule > 1:
            ctx.move_to(x0, cy)
            ctx.line_to(x0 + sign * rule, cy)
            ctx.stroke()
            diamond(ctx, x0 + sign * (rule + size * 0.28), cy, size * 0.2, C["gold"], alpha)


def wavy_underline(ctx: cairo.Context, x0: float, x1: float, y: float, col, alpha: float = 1.0,
                   progress: float = 1.0, amp: float = 4.0) -> None:
    if progress <= 0:
        return
    xe = lerp(x0, x1, clamp(progress))
    ctx.move_to(x0, y)
    x = x0
    while x < xe:
        x = min(x + 4, xe)
        ctx.line_to(x, y + amp * math.sin((x - x0) / 14))
    rgb(ctx, col, alpha)
    ctx.set_line_width(3)
    ctx.stroke()


def caption(ctx: cairo.Context, words: list[tuple[str, float]], t: float, gold: Iterable[str] = (),
            size: float = 50, y: float = CAPTION_Y, max_w: float = CAPTION_MAX_W, plate: bool = True) -> None:
    """Word-timed caption in a narrow centred column (up to 2 lines). words = [(word, start_time)].
    Key words in gold with a hand-drawn wavy underline; each word pops on its start time."""
    gold = {g.lower().strip(".,?!") for g in gold}
    font(ctx, size)
    space = ctx.text_extents(" ").x_advance
    lines, cur, cw = [], [], 0.0
    for wd, t0 in words:
        ww = ctx.text_extents(wd).x_advance
        if cur and cw + space + ww > max_w:
            lines.append((cur, cw))
            cur, cw = [], 0.0
        cur.append((wd, t0, ww))
        cw += (space if cw else 0) + ww
    if cur:
        lines.append((cur, cw))
    lh = size * 1.25
    top = y - lh * (len(lines) - 1)
    first = min((t0 for wd, t0 in words), default=0.0)
    pa = ease_out(ramp(t, first - 0.1, 0.25))
    if plate and pa > 0 and lines:
        bw = max(lw for _, lw in lines) + 90
        rounded_rect(ctx, W / 2 - bw / 2, top - size * 1.05, bw, lh * len(lines) + size * 0.55, 18)
        rgb(ctx, C["papyrus"], 0.88 * pa)
        ctx.fill_preserve()
        rgb(ctx, C["gold"], 0.7 * pa)
        ctx.set_line_width(2)
        ctx.stroke()
    for li, (ln, lw) in enumerate(lines):
        x = W / 2 - lw / 2
        yy = top + li * lh
        for wd, t0, ww in ln:
            k = ramp(t, t0, 0.18)
            if k > 0:
                is_gold = wd.lower().strip(".,?!") in gold
                wob = math.sin(hash(wd) % 7) * 0.012  # slight hand-set wobble
                text(ctx, wd, x + ww / 2, yy + (1 - ease_out(k)) * 14, size,
                     C["gold"] if is_gold else C["ink"], alpha=k, rot=wob)
                if is_gold:
                    wavy_underline(ctx, x, x + ww, yy + 12, C["gold"], k, ramp(t, t0 + 0.1, 0.35))
            x += ww + space


# ---------------------------------------------------------------- finish: grain + vignette

_GRAIN: Optional[cairo.ImageSurface] = None
_GRAIN_BUF = None  # keeps the grain pixel buffer alive


def _grain_surface() -> cairo.ImageSurface:
    global _GRAIN, _GRAIN_BUF
    if _GRAIN is None:
        rng = np.random.default_rng(7)
        n = 640
        a = (rng.random((n, n)) * 255).astype(np.uint8)
        stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A8, n)
        buf = np.zeros((n, stride), dtype=np.uint8)
        buf[:, :n] = a
        _GRAIN = cairo.ImageSurface.create_for_data(memoryview(buf), cairo.FORMAT_A8, n, n, stride)
        _GRAIN_BUF = buf
    return _GRAIN


def finish(ctx: cairo.Context, frame: int, vignette: float = 0.35) -> None:
    g = _grain_surface()
    ctx.save()
    pat = cairo.SurfacePattern(g)
    pat.set_extend(cairo.EXTEND_REPEAT)
    m = cairo.Matrix()
    m.translate((frame * 137) % 640, (frame * 251) % 640)
    pat.set_matrix(m)
    rgb(ctx, C["ink"], GRAIN_ALPHA)
    ctx.mask(pat)
    if vignette:
        rg = cairo.RadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95)
        rg.add_color_stop_rgba(0, 0, 0, 0, 0)
        rg.add_color_stop_rgba(1, C["ink"][0], C["ink"][1], C["ink"][2], vignette)
        ctx.set_source(rg)
        ctx.paint()
    ctx.restore()


# ---------------------------------------------------------------- caching + output


def cached(draw: Callable[[cairo.Context], None]) -> cairo.ImageSurface:
    """Pre-render a static layer once (backgrounds), then blit it every frame."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    draw(cairo.Context(s))
    return s


def render(draw: Callable[[cairo.Context, float, int], None], duration: float, out: Path,
           fps: int = FPS, still_at: Optional[float] = None) -> Path:
    """Render draw(ctx, t, frame) to an H.264 MP4 at 1920x1080. still_at renders one PNG instead."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    if still_at is not None:
        draw(ctx, still_at, int(still_at * fps))
        finish(ctx, int(still_at * fps))
        surf.write_to_png(str(out))
        return out
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    n = int(round(duration * fps))
    for i in range(n):
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_SOURCE)
        ctx.set_source_rgb(0, 0, 0)
        ctx.paint()
        ctx.restore()
        draw(ctx, i / fps, i)
        finish(ctx, i)
        surf.flush()
        p.stdin.write(bytes(surf.get_data()))
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")
    return out
