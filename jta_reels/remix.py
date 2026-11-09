"""Remix an existing Short into a new trial reel: a new hook card, new cuts, same voice and visuals.

Zero voice credits. This is the recipe used by hand on 9 Nov 2026, as code, so every
remix comes out the same way (and the Creator can call it later).

  python -m jta_reels.remix spec.json

spec.json:
  {"src": "prayer.mp4", "out": "trial-005-prayer.mp4",
   "segments": [[0, 41.95], [58.3, 81.15]],       # source seconds to keep, joined by 0.3 s crossfades
   "hook": ["YOU DON'T NEED", "THE RIGHT WORDS"],  # small white line, big gold line
   "hook_top": 780, "hook_height": 300,            # where the card sits (1080x1920 frame)
   "hook_seconds": 2.4,
   "masks": [[x, y, w, h, t0, t1], ...]}           # optional: blur out a stale label (output seconds)

Prints the output's duration and loudness, and writes contact sheets of the first frame,
every join and the last frame for a human or vision check.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1920
XFADE = 0.3
FONT = "IM FELL DW Pica"
GOLD = (232 / 255, 176 / 255, 75 / 255)
OFF_WHITE = (0.95, 0.93, 0.88)


def hook_png(lines: list[str], out: Path, top: int = 780, height: int = 300, opaque: bool = False) -> Path:
    """The series' title-card look: dark band, thin gold rules, small white line over a big gold line."""
    import cairo
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(s)
    c.rectangle(0, top, W, height)
    c.set_source_rgba(8 / 255, 10 / 255, 20 / 255, 1.0 if opaque else 0.86)
    c.fill()
    for y in (top + 40, top + height - 40):
        c.move_to(150, y)
        c.line_to(W - 150, y)
        c.set_source_rgba(*GOLD, 0.8)
        c.set_line_width(2)
        c.stroke()

    def line(txt: str, size: float, rgb, baseline: float, spacing: float, max_w: float = 940) -> None:
        c.select_font_face(FONT)
        while True:
            c.set_font_size(size)
            ws = [c.text_extents(ch).x_advance for ch in txt]
            total = sum(ws) + spacing * (len(txt) - 1)
            if total <= max_w or size < 30:
                break
            size -= 2
        x = (W - total) / 2
        for ch, w in zip(txt, ws):
            c.move_to(x, baseline)
            c.set_source_rgba(*rgb, 1)
            c.show_text(ch)
            x += w + spacing

    small, big = lines
    mid = top + height / 2                      # the two lines sit as a pair in the middle of the band
    line(small, 50, OFF_WHITE, mid - 28, 4)
    line(big, 80, GOLD, mid + 72, 3)
    s.write_to_png(str(out))
    return out


def render(spec: dict, workdir: Path) -> Path:
    src, out = Path(spec["src"]), Path(spec["out"])
    segs = spec["segments"]
    hook = hook_png(spec["hook"], workdir / f"{out.stem}-hook.png", spec.get("hook_top", 780),
                    spec.get("hook_height", 300), spec.get("hook_opaque", False))
    hs = float(spec.get("hook_seconds", 2.4))
    hf = float(spec.get("hook_fade", 0.3))          # short fade when the card hides old on-screen text
    parts, joins, t = [], [], 0.0
    for i, (a, b) in enumerate(segs):
        parts.append(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS[a{i}]")
    v, a = "v0", "a0"
    t = segs[0][1] - segs[0][0]
    for i in range(1, len(segs)):
        off = t - XFADE
        parts.append(f"[{v}][v{i}]xfade=transition=fade:duration={XFADE}:offset={off:.3f}[vx{i}];"
                     f"[{a}][a{i}]acrossfade=d={XFADE}[ax{i}]")
        joins.append(off + XFADE / 2)
        v, a = f"vx{i}", f"ax{i}"
        t = off + (segs[i][1] - segs[i][0])
    total = t
    for j, (x, y, w, h, t0, t1) in enumerate(spec.get("masks", [])):
        parts.append(f"[{v}]delogo=x={x}:y={y}:w={w}:h={h}:enable='between(t,{t0},{t1})'[vm{j}]")
        v = f"vm{j}"
    parts.append(f"[1:v]format=rgba,fade=t=out:st={hs - hf:.2f}:d={hf}:alpha=1[hk];"
                 f"[{v}][hk]overlay=0:0:eof_action=pass,fade=t=out:st={total - 0.35:.2f}:d=0.35[vout];"
                 f"[{a}]afade=t=out:st={total - 0.5:.2f}:d=0.5[aout]")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-loop", "1", "-t", f"{hs}", "-i", str(hook),
           "-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
           "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)

    # checks: duration, loudness, and a contact sheet of the moments most likely to go wrong
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(out)], capture_output=True, text=True, check=True).stdout)
    ebu = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    lufs = next((ln.split()[1] for ln in ebu.splitlines() if ln.strip().startswith("I:")), "?")
    moments = [0.5, hs + 0.4] + [x for j in joins for x in (j - 0.6, j + 0.6)] + [dur - 1.0]
    shots = []
    for k, m in enumerate(moments):
        p = workdir / f"{out.stem}-chk{k:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m:.2f}", "-i", str(out), "-frames:v", "1", "-vf",
                        f"scale=216:-1,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                        f"text='{m:.1f}':x=4:y=4:fontsize=16:fontcolor=yellow:box=1:boxcolor=black", str(p)], check=True)
        shots.append(p)
    sheet = workdir / f"{out.stem}-check.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *sum([["-i", str(p)] for p in shots], []),
                    "-filter_complex", f"hstack=inputs={len(shots)}", str(sheet)], check=True)
    print(json.dumps({"out": str(out), "duration_s": round(dur, 2), "loudness_lufs": lufs,
                      "joins_at_s": [round(j, 2) for j in joins], "check_sheet": str(sheet)}))
    return out


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text())
    render(spec, Path(spec.get("workdir", ".")))
