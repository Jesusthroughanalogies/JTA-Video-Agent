"""ffmpeg helpers: probe, QC frames, the JTA grade, cards and the cut.

Every output is written to a .part file and renamed when complete, so a kill
mid-render never leaves a half file that looks finished.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from jta_visuals import rules

FONT = os.environ.get("JTA_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {shlex.join(cmd)[:300]}\n{r.stderr[-1500:]}")


def _ff(out: Path, args: list[str]) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.stem + ".part" + out.suffix)
    run(["ffmpeg", "-y", "-loglevel", "error", *args, str(part)])
    os.replace(part, out)
    return out


def done(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 0


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def qc_frames(clip: Path, out_dir: Path) -> list[Path]:
    """Start, middle and end frames for checking a clip (Phase 5 step 5)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if clip.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return [clip]
    d = duration(clip)
    frames = []
    for name, t in (("start", 0.1), ("mid", d / 2), ("end", max(0.0, d - 0.2))):
        f = out_dir / f"{clip.stem}_{name}.jpg"
        if not done(f):
            _ff(f, ["-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", "-q:v", "3"])
        frames.append(f)
    return frames


def grade(src: Path, out: Path) -> Path:
    """Apply the locked JTA grade (Section 5.5) to an AI clip."""
    if done(out):
        return out
    return _ff(out, ["-i", str(src), "-vf", rules.GRADE_FILTER, "-an", "-c:v", "libx264",
                     "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"])


def card(text: str, out: Path, seconds: float, size: str = "1920x1080", bg: Path | None = None) -> Path:
    """Plain placeholder card (dark umber, papyrus text) for dry runs and shots with no scene yet."""
    if done(out):
        return out
    safe = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")
    w = int(size.split("x")[0])
    draw = (f"drawtext=fontfile={FONT}:text='{safe}':fontcolor=0xE9DCC0:fontsize={w // 32}:"
            f"x=(w-text_w)/2:y=(h-text_h)/2")
    if bg:
        args = ["-stream_loop", "-1", "-t", f"{seconds:.2f}", "-i", str(bg),
                "-vf", f"scale={size.replace('x', ':')},eq=brightness=-0.25,{draw}"]
    else:
        args = ["-f", "lavfi", "-t", f"{seconds:.2f}", "-i", f"color=c=0x211812:s={size}:r=30", "-vf", draw]
    return _ff(out, args + ["-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"])


def tone(seconds: float, out: Path, freq: int = 220) -> Path:
    """Dry-run stand-in for a voice line."""
    if done(out):
        return out
    return _ff(out, ["-f", "lavfi", "-t", f"{seconds:.2f}", "-i", f"sine=frequency={freq}:sample_rate=44100",
                     "-af", "volume=0.2", "-ac", "1"])


def segment(src: Path, seconds: float, out: Path, size: str, still_motion: bool = True) -> Path:
    """One timeline shot, normalised to size and 30 fps, trimmed or looped to its slot."""
    if done(out):
        return out
    w, h = size.split("x")
    fit = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        frames = max(1, int(seconds * 30))
        vf = (f"scale={int(w) * 2}:{int(h) * 2}:force_original_aspect_ratio=increase,crop={int(w) * 2}:{int(h) * 2},"
              f"zoompan=z='min(zoom+0.0006,1.08)':d={frames}:s={size}:fps=30,setsar=1") if still_motion else fit
        args = ["-loop", "1", "-t", f"{seconds:.2f}", "-i", str(src), "-vf", vf]
    else:
        args = ["-stream_loop", "-1", "-t", f"{seconds:.2f}", "-i", str(src), "-vf", fit]
    return _ff(out, args + ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                            "-t", f"{seconds:.2f}"])


def concat_audio(files: list[Path], out: Path, gap: float = 0.25) -> Path:
    if done(out):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_suffix(".txt")
    silence = out.parent / f"_gap_{gap:.2f}.wav"
    if not done(silence):
        _ff(silence, ["-f", "lavfi", "-t", f"{gap}", "-i", "anullsrc=r=44100:cl=mono"])
    lines = []
    for f in files:
        lines += [f"file '{f.resolve()}'", f"file '{silence.resolve()}'"]
    lst.write_text("\n".join(lines) + "\n")
    return _ff(out, ["-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "44100", "-ac", "1"])


def render_cut(segments: list[Path], audio: Path | None, out: Path, loudnorm: bool = True) -> Path:
    """Concatenate normalised segments and lay the narration under them."""
    if done(out):
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segments))
    args = ["-f", "concat", "-safe", "0", "-i", str(lst)]
    if audio:
        args += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
        if loudnorm:
            args += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]  # style bible: about -14 LUFS final
    return _ff(out, args + ["-c:v", "copy", "-movflags", "+faststart"])
