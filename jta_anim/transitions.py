"""The paint-over transition between AI footage and animation (Matt, 2 Nov 2026: the jump from
AI to animated is too drastic).

AI -> animation: the live frame is painted over (colours pulled into the earth palette, ink
outlines drawn on, papyrus grain), the temple frame closes in around it, then brush strokes
paint the animated scene in. Animation -> AI runs the same steps backwards: brush strokes wipe the
animation away to a painted version of the next AI shot, which then comes alive.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cairo
import cv2
import numpy as np

from . import egypt
from .theme import FPS, H, PAL, W

DUR = 1.4  # seconds

# palette the footage is painted into (BGR), darkest to lightest
_PAINT = [PAL[k] for k in ("night_bg", "ink", "bronze", "terracotta", "olive", "indigo", "gold", "sun",
                           "stone_shade", "dune_mid", "stone_lit", "papyrus", "limestone")]
PAINT_BGR = np.array([[int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16)] for h in _PAINT], np.float32)
INK = np.array([0x1D, 0x2A, 0x3A], np.float32)


def _bgr(h):
    h = PAL[h]
    return [int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16)]


RAMP = [(0.0, _bgr("night_bg")), (0.3, [(i + k) // 2 for i, k in zip(_bgr("indigo"), _bgr("ink"))]), (0.55, _bgr("bronze")), (0.8, _bgr("sun")),
        (1.0, _bgr("papyrus"))]
PAPYRUS = np.array([0xC0, 0xDC, 0xE9], np.float32) / 255.0


def _ease(u):
    u = min(max(u, 0.0), 1.0)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def painted(frame: np.ndarray) -> np.ndarray:
    """The frame as a flat ink-and-wash painting in the JTA style (float32 BGR 0..255): tones
    banded into a few flat steps, colour pulled warm toward the earth palette, umber outlines."""
    small = cv2.resize(frame, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    smooth = cv2.edgePreservingFilter(small, flags=1, sigma_s=40, sigma_r=0.35)
    lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0]
    lo, hi = np.percentile(L, 2), np.percentile(L, 99.5)
    Ln = np.clip((L - lo) / max(hi - lo, 1), 0, 1)
    steps = 5
    band = np.floor(Ln * steps) / (steps - 1)
    soft = np.clip((Ln * steps - np.floor(Ln * steps) - 0.85) / 0.15, 0, 1) / (steps - 1)
    Lq = np.clip(band + soft, 0, 1)
    lab[..., 0] = 28 + Lq * 200                 # never pure black or pure white
    lab[..., 1] = 128 + (lab[..., 1] - 128) * 0.75 + 3
    lab[..., 2] = 128 + (lab[..., 2] - 128) * 0.75 + 8   # warm: toward ochre
    flat = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
    # map the tones onto the JTA palette (umber shadows, indigo, bronze, gold, papyrus highlights)
    ramp = np.zeros_like(flat)
    xs = np.array([s for s, _ in RAMP], np.float32)
    for c in range(3):
        ramp[..., c] = np.interp(Lq, xs, np.array([col[c] for _, col in RAMP], np.float32))
    flat = 0.6 * ramp + 0.4 * flat
    gray = cv2.cvtColor(smooth, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 30, 90)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    e = cv2.GaussianBlur(edges.astype(np.float32) / 255.0, (3, 3), 0)[..., None]
    flat = flat * (1 - e) + INK * e
    flat = cv2.resize(flat, (W, H), interpolation=cv2.INTER_LINEAR)
    # paper grain
    rng = np.random.default_rng(1)
    grain = rng.normal(0, 6, (H // 4, W // 4)).astype(np.float32)
    grain = cv2.resize(grain, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
    return flat * (0.88 + 0.12 * PAPYRUS) + grain


_FRAME = None


def temple_frame() -> np.ndarray:
    """The temple frame (columns, frieze, bottom band) as BGRA float, transparent elsewhere."""
    global _FRAME
    if _FRAME is None:
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        egypt.frame(cairo.Context(s))
        a = np.ndarray((H, W, 4), np.uint8, s.get_data()).astype(np.float32)
        _FRAME = a  # premultiplied BGRA
    return _FRAME


def _over_frame(img: np.ndarray, k: float) -> np.ndarray:
    """Composite the temple frame over img, closing in from outside the screen as k goes 0 -> 1."""
    if k <= 0:
        return img
    fr = temple_frame()
    sc = 1.0 + 0.12 * (1 - k)
    M = np.float32([[sc, 0, W / 2 * (1 - sc)], [0, sc, H / 2 * (1 - sc)]])
    f = cv2.warpAffine(fr, M, (W, H))
    alpha = f[..., 3:4] / 255.0 * k
    return img * (1 - alpha) + f[..., :3] * k


def _brush_mask(u: float, seed: int = 4) -> np.ndarray:
    """1 where the new scene has been painted in. Nine ragged horizontal strokes, staggered."""
    rng = np.random.default_rng(seed)
    n = 7
    bh = H / n
    xs = np.arange(W, dtype=np.float32)
    m = np.zeros((H, W), np.float32)
    for i in range(n):
        start = rng.uniform(0, 0.35)
        p = min(max((u - start) / 0.65, 0.0), 1.0)
        p = 1 - (1 - p) ** 2
        lead = p * (W + 300) - 150
        y0, y1 = int(i * bh - 12), int((i + 1) * bh + 12)
        y0, y1 = max(y0, 0), min(y1, H)
        rows = np.arange(y0, y1)
        jag = 40 * np.sin(rows * 0.05 + i * 2.1) + 18 * np.sin(rows * 0.17 + i)
        bristle = np.repeat(rng.normal(0, 1, len(rows) // 3 + 1), 3)[: len(rows)] * 22   # dry-brush streaks
        edge = (lead + jag + bristle)[:, None]
        band = np.clip((edge - xs[None, :]) / 70.0, 0, 1)
        if i % 2:
            band = band[:, ::-1]   # alternate strokes run right to left, like a painter's hand
        m[y0:y1] = np.maximum(m[y0:y1], band)
    return cv2.GaussianBlur(m, (0, 0), 3)[..., None]


def _frames(path: Path, n: int, from_end: bool) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start = max(total - n, 0) if from_end else 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    out = []
    while len(out) < n:
        ok, f = cap.read()
        if not ok:
            if not out:
                raise RuntimeError(f"no frames in {path}")
            out.append(out[-1])
            continue
        if f.shape[:2] != (H, W):
            f = cv2.resize(f, (W, H))
        out.append(f)
    cap.release()
    return out


PAINT_S, HOLD_S, BRUSH_S = 0.8, 2.2, 0.9   # Matt, 2 Nov 2026: sit on the painted version longer


def _bright_point(img: np.ndarray) -> tuple[float, float]:
    g = cv2.GaussianBlur(cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY), (0, 0), 25)
    y, x = np.unravel_index(int(g.argmax()), g.shape)
    return float(x), float(y)


class _Life:
    """Brings the painted still to life: slow push toward the light, a pulsing glow there,
    gold stars twinkling in the dark areas and dust drifting through the air."""

    def __init__(self, still: np.ndarray, seed: int = 3):
        self.still = still
        self.bx, self.by = _bright_point(still)
        rng = np.random.default_rng(seed)
        lum = cv2.cvtColor(np.clip(still, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        ys, xs = np.where(lum[60:H - 40:8, 150:W - 150:8] < np.percentile(lum, 35))
        pick = rng.choice(len(xs), size=min(28, len(xs)), replace=False) if len(xs) else []
        self.stars = [(150 + xs[i] * 8, 60 + ys[i] * 8, rng.uniform(0, 6.28), rng.uniform(2.5, 5)) for i in pick]
        self.dust = [(rng.uniform(150, W - 150), rng.uniform(80, H - 60), rng.uniform(0, 6.28), rng.uniform(1.5, 3.5))
                     for _ in range(45)]
        self.gold = np.array(_bgr("gold"), np.float32)
        self.sun = np.array(_bgr("sun"), np.float32)
        self.pap = np.array(_bgr("papyrus"), np.float32)

    def frame(self, t: float, zoom: float) -> np.ndarray:
        # push toward the light
        cx = W / 2 + (self.bx - W / 2) * 0.35
        cy = H / 2 + (self.by - H / 2) * 0.35
        M = np.float32([[zoom, 0, cx * (1 - zoom)], [0, zoom, cy * (1 - zoom)]])
        img = cv2.warpAffine(self.still, M, (W, H), borderMode=cv2.BORDER_REFLECT)
        bx, by = self.bx * zoom + cx * (1 - zoom), self.by * zoom + cy * (1 - zoom)
        # glow pulse at the light
        yy, xx = np.ogrid[:H, :W]
        d2 = ((xx - bx) ** 2 + (yy - by) ** 2) / (260.0 ** 2)
        g = (np.exp(-d2) * (0.16 + 0.08 * np.sin(t * 3.0)))[..., None]
        img = img * (1 - g) + self.sun * g
        over = np.zeros((H, W, 3), np.float32)
        alpha = np.zeros((H, W), np.float32)
        for x, y, ph, r in self.stars:      # twinkling four-point stars
            a = max(0.0, np.sin(t * 2.2 + ph)) ** 2
            if a < 0.05:
                continue
            x, y = int(x * zoom + cx * (1 - zoom)), int(y * zoom + cy * (1 - zoom))
            L = int(r * 3)
            cv2.line(alpha, (x - L, y), (x + L, y), float(a), 2, cv2.LINE_AA)
            cv2.line(alpha, (x, y - L), (x, y + L), float(a), 2, cv2.LINE_AA)
            cv2.circle(alpha, (x, y), int(r * 0.6) + 1, float(a), -1, cv2.LINE_AA)
        over[:] = self.gold
        img = img * (1 - alpha[..., None]) + over * alpha[..., None]
        dust = np.zeros((H, W), np.float32)
        for x, y, ph, r in self.dust:       # dust drifting up and sideways
            px = int((x + 25 * np.sin(t * 0.8 + ph)) % W)
            py = int((y - 30 * t) % H)
            cv2.circle(dust, (px, py), int(r), 0.35 + 0.25 * float(np.sin(t * 2 + ph)), -1, cv2.LINE_AA)
        dust = cv2.GaussianBlur(dust, (0, 0), 1.2)[..., None]
        return img * (1 - dust) + self.pap * dust


def transition(ai_clip: Path, anim_clip: Path, out: Path, *, to_anim: bool = True,
               paint: float = PAINT_S, hold: float = HOLD_S, brush: float = BRUSH_S) -> Path:
    """AI -> animation: footage is painted over (paint), the painting comes alive (hold), then
    brush strokes paint the animation in (brush). Animation -> AI runs the same steps backwards.
    Uses paint seconds of the AI clip and brush seconds of the animation."""
    n_p, n_h, n_b = (int(round(x * FPS)) for x in (paint, hold, brush))
    ai = _frames(ai_clip, n_p, from_end=to_anim)
    an = _frames(anim_clip, n_b, from_end=not to_anim)
    still = painted(ai[-1] if to_anim else ai[0])
    life = _Life(still)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    total = n_p + n_h + n_b
    zmax = 1.09

    def emit(img):
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())

    for i in range(total):
        t = i / FPS
        if to_anim:
            if i < n_p:                                      # live footage becomes the painting
                s = _ease(i / max(n_p - 1, 1))
                img = ai[i].astype(np.float32) * (1 - s) + life.frame(t, 1.0) * s
                emit(_over_frame(img, s))
            elif i < n_p + n_h:                              # the painting comes alive
                k = (i - n_p) / max(n_h - 1, 1)
                emit(_over_frame(life.frame(t, 1.0 + (zmax - 1) * _ease(k)), 1.0))
            else:                                            # brush the animation in
                j = i - n_p - n_h
                m = _brush_mask(j / max(n_b - 1, 1))
                img = life.frame(t, zmax) * (1 - m) + an[j].astype(np.float32) * m
                emit(_over_frame(img, 1.0))
        else:
            if i < n_b:                                      # brush the animation away
                m = _brush_mask(i / max(n_b - 1, 1), seed=7)
                img = an[i].astype(np.float32) * (1 - m) + life.frame(t, zmax) * m
                emit(_over_frame(img, 1.0))
            elif i < n_b + n_h:                              # the painting lives, easing back out
                k = (i - n_b) / max(n_h - 1, 1)
                emit(_over_frame(life.frame(t, zmax - (zmax - 1) * _ease(k)), 1.0))
            else:                                            # and comes alive as real footage
                j = i - n_b - n_h
                s = 1 - _ease(j / max(n_p - 1, 1))
                img = ai[j].astype(np.float32) * (1 - s) + life.frame(t, 1.0) * s
                emit(_over_frame(img, s))
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")
    return out
