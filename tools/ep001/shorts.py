"""Three 9:16 Shorts cut from the Ep 1 master, in the JTA papyrus frame with big word-timed captions."""
import json
import subprocess
import sys

import cairo

sys.path.insert(0, "/home/claude/jta-video-agent")
from jta_anim import egypt  # noqa: E402
from jta_anim.core import label, outline_fill, rounded_rect, text  # noqa: E402
from jta_anim.theme import C  # noqa: E402

MASTER = "/tmp/cut/JTA_Ep1_MASTER_1080p.mp4"
OUT = "/tmp/cut/shorts"
W, H = 1080, 1920
VY, VH = 520, 630              # video band
PLAN = json.load(open("/tmp/cut/v2/plan.json"))

SHORTS = [
    ("01_dominoes", "WHO PUSHED THE", "FIRST DOMINO?", [(38.4, 109.0)]),
    ("02_dials", "WHO SET", "THE DIALS?", [(169.5, 200.8), (231.75, 239.2)]),
    ("03_the_painter", "THE PAINTER STEPPED", "INTO HIS PAINTING",
     [(306.2, 317.0), (332.75, 335.75), (424.33, 432.6), (465.37, 470.8), (477.2, 487.1), (512.1, 515.4)]),
]


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def background(path, l1, l2):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(s)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, *C["sky_top"])
    g.add_color_stop_rgb(1, *C["papyrus_dark"])
    ctx.set_source(g)
    ctx.paint()
    egypt._frieze(ctx)                      # top band
    ctx.save()
    ctx.translate(0, H - 1080)
    egypt._zigzag(ctx)                      # bottom band
    ctx.restore()
    text(ctx, l1, W / 2, 300, 68, C["ink"], spacing=6, shadow=True)
    text(ctx, l2, W / 2, 400, 80, C["gold"], spacing=6, shadow=True)
    rounded_rect(ctx, -10, VY - 22, W + 20, VH + 44, 6)   # bronze frame around the scene
    outline_fill(ctx, C["bronze"])
    label(ctx, "Full video · Is there a God?", W / 2, 1700, 30)
    text(ctx, "Jesus Through Analogies", W / 2, 1765, 34, C["bronze"], italic=True)
    s.write_to_png(path)


def words_in(ranges):
    """Arthur's words inside the ranges, re-timed to the Short's own clock."""
    out, base = [], 0.0
    for a, b in ranges:
        for sl in PLAN["slots"]:
            for w, t in sl["words"]:
                at = sl["start"] + t
                if a <= at < b - 0.3:
                    out.append((w, base + at - a))
        base += b - a
    return out


def ass(path, words, total):
    def ts(x):
        return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            "Style: Cap,IM FELL DW Pica,92,&H001D2A3A,&H002F86B8,&H00C0DCE9,&H00000000,0,0,0,0,100,100,1,0,1,6,0,5,40,40,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    chunks, cur = [], []
    for w, t in words:
        cur.append((w, t))
        if len(cur) == 3 or w[-1:] in ".?!,:;":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    lines = []
    for i, c in enumerate(chunks):
        t0 = c[0][1]
        t1 = chunks[i + 1][0][1] if i + 1 < len(chunks) else total
        t1 = min(t1, t0 + 2.6)
        # karaoke: each word turns gold as it is said
        kar = "".join(f"{{\\k{max(int(((c[j + 1][1] if j + 1 < len(c) else t1) - c[j][1]) * 100), 1)}}}{c[j][0]} "
                      for j in range(len(c)))
        lines.append(f"Dialogue: 0,{ts(t0)},{ts(t1)},Cap,,0,0,0,,{{\\pos(540,1340)\\fad(80,60)}}{kar.strip()}")
    open(path, "w").write(head + "\n".join(lines) + "\n")


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    for name, l1, l2, ranges in SHORTS:
        if only and name not in only:
            continue
        bg = f"{OUT}/{name}_bg.png"
        background(bg, l1, l2)
        total = sum(b - a for a, b in ranges)
        sub = f"{OUT}/{name}.ass"
        ass(sub, words_in(ranges), total)
        parts = []
        for i, (a, b) in enumerate(ranges):     # cut each section on its own (fast seek, low memory)
            pth = f"{OUT}/{name}_part{i}.mp4"
            run("-ss", f"{a:.3f}", "-i", MASTER, "-t", f"{b - a:.3f}", "-vf",
                f"crop=1360:794:280:68,scale=1080:{VH},fps=30", "-af",
                f"afade=t=in:d=0.2,afade=t=out:st={b - a - 0.25:.3f}:d=0.25", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", pth)
            parts.append(pth)
        lst = f"{OUT}/{name}_parts.txt"
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        joined = f"{OUT}/{name}_joined.mp4"
        run("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined)
        run("-i", joined, "-loop", "1", "-i", bg, "-filter_complex",
            f"[1:v][0:v]overlay=0:{VY}:shortest=1,ass={sub},format=yuv420p[ov];"
            f"[0:a]afade=t=out:st={total - 0.8:.3f}:d=0.8[ao]",
            "-map", "[ov]", "-map", "[ao]", "-t", f"{total:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", f"{OUT}/JTA_Ep1_Short_{name}.mp4")
        print(name, round(total, 1), "s", flush=True)
