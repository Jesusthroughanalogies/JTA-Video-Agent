"""python -m jta_reels.shorts OUT_DIR [slug ...] [--stills t1,t2,...] [--align slug=words.json]"""
import argparse
import json
from pathlib import Path

from .engine import render, still
from .reels import ALL

p = argparse.ArgumentParser()
p.add_argument("out")
p.add_argument("slugs", nargs="*")
p.add_argument("--stills", help="comma-separated times: render PNG stills instead of video")
p.add_argument("--align", action="append", default=[], help="slug=words.json (real voice timings)")
p.add_argument("--audio", action="append", default=[], help="slug=voice.mp3")
a = p.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
aligns = dict(x.split("=", 1) for x in a.align)
audios = dict(x.split("=", 1) for x in a.audio)
for slug in a.slugs or list(ALL):
    r = ALL[slug].time_estimate()
    if slug in aligns:
        r.apply_alignment(Path(aligns[slug]))
    (out / f"{slug}.script.txt").write_text(r.script() + "\n")
    (out / f"{slug}.timeline.json").write_text(json.dumps(
        {"total_s": round(r.total, 2), "beats": {k: [round(v[0], 2), round(v[1], 2)] for k, v in r.beat_t.items()}},
        indent=1))
    if a.stills:
        for t in a.stills.split(","):
            if t.startswith("b") and t not in r.beat_t:
                continue
            tt = float(t) if not t.startswith("b") else r.B(t) + 0.8
            still(r, tt, out / f"{slug}-{t}.png")
    else:
        render(r, out / f"{slug}.mp4", Path(audios[slug]) if slug in audios else None)
    print(slug, f"{r.total:.1f}s", len(r.script()), "chars")
