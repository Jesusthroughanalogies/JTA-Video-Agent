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


def transition(ai_clip: Path, anim_clip: Path, out: Path, *, to_anim: bool = True, dur: float = DUR) -> Path:
    """Render the paint-over transition. to_anim: AI tail -> animation head; else animation tail -> AI head."""
    n = int(round(dur * FPS))
    ai = _frames(ai_clip, n, from_end=to_anim)
    an = _frames(anim_clip, n, from_end=not to_anim)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                          "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for i in range(n):
        u = i / max(n - 1, 1)
        if to_anim:
            s = _ease(u / 0.55)                      # paint over the footage
            w = (u - 0.45) / 0.55                    # then brush the animation in
            src = ai[i].astype(np.float32)
            img = src * (1 - s) + painted(ai[i]) * s if s > 0 else src
            if w > 0:   # the brush works inside the frame; the temple frame stays solid on top
                m = _brush_mask(w)
                img = img * (1 - m) + an[i].astype(np.float32) * m
            img = _over_frame(img, s)
        else:
            w = u / 0.55                             # brush the animation away to the painted footage
            s = 1 - _ease((u - 0.45) / 0.55)         # which then comes alive
            src = ai[i].astype(np.float32)
            img = src * (1 - s) + painted(ai[i]) * s if s > 0 else src
            m = _brush_mask(min(max(w, 0), 1), seed=7)
            img = an[i].astype(np.float32) * (1 - m) + img * m
            img = _over_frame(img, max(s, 1.0 - float(m.mean())))
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")
    return out
