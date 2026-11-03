"""Ep 1 Short 4: 'Is there a God?' in 66 s. Hook, then the three analogies with on-screen analogy banners."""
import glob
import json
import os
import subprocess
import sys

import cairo

sys.path.insert(0, "/tmp/cut")
sys.path.insert(0, "/home/claude/jta-video-agent")
import shorts as SH  # noqa: E402
from jta_anim.core import outline_fill, rounded_rect, text  # noqa: E402
from jta_anim.theme import C  # noqa: E402

G = "/tmp/cut/graded"
SEG = "/tmp/cut/v2/seg"
OUT = "/tmp/s4"
WORDS = json.load(open(f"{OUT}/words.json"))["words"]
VH, VY = SH.VH, SH.VY
FINAL = "/tmp/cut/shorts/JTA_Ep1_Short_04_is_there_a_god.mp4"


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def g(prefix):
    return [p for p in glob.glob(f"{G}/{prefix}*.mp4") if not p.endswith("_boom.mp4")][0]


def seg(sid):
    return glob.glob(f"{SEG}/*_{sid}.mp4")[0]


# (start, end, source, kind, offset into source; None = take the end of an animation)
EDIT = [
    # HOOK
    (0.0, 1.45, g("b60a0d6b"), "ai", 0.5),      # Is there a God?  (lone man, cliff, stars)
    (1.45, 2.85, g("dfa96902"), "ai", 1.0),     # give me sixty seconds (nebula)
    (2.85, 3.45, seg("P1-01"), "anim", 1.5),    # and three... flash: dominoes
    (3.45, 4.05, g("b14df2a6"), "ai", 2.0),     # pictures... flash: dials
    (4.05, 4.70, g("5f1988c1"), "ai", 3.0),     # flash: painting
    (4.70, 6.00, g("af9ccc7d"), "ai", 0.5),     # then decide for yourself
    # ANALOGY 1: DOMINOES
    (6.00, 9.20, seg("P1-01"), "anim", 0.0),
    (9.20, 10.45, seg("P1-02"), "anim", 1.5),   # follow it back
    (10.45, 12.60, seg("P1-03"), "anim", None), # something had to push the first one
    (12.60, 14.30, g("87d4571a"), "ai", 0.5),   # science says the universe had a beginning
    (14.30, 16.20, seg("P1-15"), "anim", 0.3),  # so what pushed it?
    # ANALOGY 2: DIALS
    (16.20, 19.20, g("b14df2a6"), "ai", 0.0),   # a room full of dials
    (19.20, 23.90, seg("P2-02"), "anim", 1.5),  # each one sets a rule... gravity, atoms, light
    (23.90, 26.40, seg("P2-04"), "anim", None), # turn one slightly: no stars
    (26.40, 27.50, seg("P2-05"), "anim", None), # no life
    (27.50, 29.85, g("b3a043bf"), "ai", 0.5),   # every dial set just right
    (29.85, 32.25, g("77c7ed3e"), "ai", 0.5),   # accident? or did someone set them?
    # ANALOGY 3: PAINTING
    (32.25, 34.60, g("5f1988c1"), "ai", 0.3),   # a painting
    (34.60, 36.50, seg("P3-02"), "anim", None), # a painting tells you there's a painter
    (36.50, 37.85, g("08b01d5e"), "ai", 1.0),   # and what He loves
    (37.85, 39.75, g("170e420e"), "ai", 1.0),   # a sunrise nobody needed
    (39.75, 42.45, g("9e47de7a"), "ai", 0.5),   # right and wrong in every heart
    (42.45, 46.10, g("7250e797"), "ai", 0.3),   # study a painting your whole life
    (46.10, 48.05, seg("P4-03"), "anim", None), # unless He steps into it
    (48.05, 50.55, g("941bab45"), "ai", 0.5),   # what Christians believe happened
    (50.55, 51.55, g("cbc91c7b"), "ai", 0.6),   # Jesus.
    (51.55, 52.75, g("5ab69173"), "ai", 1.8),   # He fed the poor
    (52.75, 54.85, g("1e15c5a7"), "ai", 1.0),   # touched the people nobody would touch
    (54.85, 57.25, g("91600f8a"), "ai", 1.0),   # forgave the people who killed Him
    # PAYOFF
    (57.25, 63.55, seg("P4-15"), "anim", 0.8),  # dominoes / dials / painting recap
    (63.55, 67.20, seg("P4-16"), "anim", None), # Jesus says He came looking for you
]
TOTAL = 67.2

# analogy banners: (start, end, small line, big line)
BANNERS = [
    (2.85, 3.45, "ANALOGY I", "THE DOMINOES"),
    (3.45, 4.05, "ANALOGY II", "THE DIALS"),
    (4.05, 4.70, "ANALOGY III", "THE PAINTING"),
    (6.00, 16.20, "ANALOGY I", "THE DOMINOES"),
    (16.20, 32.25, "ANALOGY II", "THE DIALS"),
    (32.25, 57.25, "ANALOGY III", "THE PAINTING"),
]


def banner_png(path, small, big):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, SH.W, SH.H)
    ctx = cairo.Context(s)
    w, h = 640, 112
    x, y = (SH.W - w) / 2, VY + 18
    rounded_rect(ctx, x, y, w, h, 14)
    ctx.set_source_rgba(*C["papyrus"], 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*C["bronze"])
    ctx.set_line_width(4)
    ctx.stroke()
    text(ctx, small, SH.W / 2, y + 40, 28, C["bronze"], spacing=8)
    text(ctx, big, SH.W / 2, y + 92, 50, C["ink"], spacing=4)
    s.write_to_png(path)


if __name__ == "__main__":
    parts = []
    for i, (a, b, src, kind, off) in enumerate(EDIT):
        d = b - a
        n = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                                 capture_output=True, text=True).stdout)
        if off is None:
            off = max(n - d, 0)
        off = min(off, max(n - 0.3, 0))
        slow = max(d / max(n - off, 0.1), 1.0)
        crop = "crop=1300:760:310:68" if kind == "anim" else "crop=1440:840:240:120"
        zoom = ""
        if i == 0:   # hook: slow push-in on the opening frame
            zoom = ",zoompan=z='1+0.0016*on':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x630:fps=30"
        p = f"{OUT}/p{i:02d}.mp4"
        run("-ss", f"{off:.3f}", "-i", src, "-t", f"{min(d / slow, n - off):.3f}", "-vf",
            f"setpts={slow:.4f}*PTS,{crop},scale=1080:{VH},fps=30{zoom},tpad=stop_mode=clone:stop_duration=3",
            "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", p)
        parts.append(p)
    open(f"{OUT}/list.txt", "w").write("".join(f"file '{p}'\n" for p in parts))
    run("-f", "concat", "-safe", "0", "-i", f"{OUT}/list.txt", "-c", "copy", f"{OUT}/video.mp4")
    bg = f"{OUT}/bg.png"
    SH.background(bg, "IS THERE", "A GOD?")
    words = [(w["text"], w["start"]) for w in WORDS if w.get("type", "word") == "word"]
    SH.ass(f"{OUT}/s4.ass", words, TOTAL)
    # banners
    ins, chain, last = ["-i", f"{OUT}/video.mp4", "-loop", "1", "-i", bg], [f"[1:v][0:v]overlay=0:{VY}:shortest=1[b0]"], "b0"
    for k, (a, b, sm, bg_) in enumerate(BANNERS):
        png = f"{OUT}/banner{k}.png"
        banner_png(png, sm, bg_)
        ins += ["-loop", "1", "-i", png]
        chain.append(f"[{last}][{k + 2}:v]overlay=0:0:enable='between(t,{a},{b - 0.01})':shortest=1[b{k + 1}]")
        last = f"b{k + 1}"
    chain.append(f"[{last}]ass={OUT}/s4.ass,format=yuv420p[ov]")
    run(*ins, "-filter_complex", ";".join(chain), "-map", "[ov]", "-t", f"{TOTAL:.3f}", "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", f"{OUT}/picture.mp4")
    print("picture done", flush=True)
    # music: Icy Road (tension) under the hook and analogies, Ananda Yoga lifts on "Unless He steps into it"
    duck = "sidechaincompress=threshold=0.025:ratio=3.5:attack=40:release=500:makeup=1"
    run("-i", f"{OUT}/vo.mp3", "-i", "/tmp/music/Icy Road.mp3", "-i", "/tmp/music/Ananda Yoga.mp3", "-filter_complex",
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={TOTAL},asplit=2[v][key];"
        "[1:a]atrim=start=0:duration=47.0,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
        "afade=t=in:d=0.6,afade=t=out:st=45.4:d=1.6[m1];"
        f"[2:a]atrim=start=53.9:duration={TOTAL - 45.0:.2f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
        f"afade=t=in:d=1.4,afade=t=out:st={TOTAL - 45.0 - 2.0:.2f}:d=2.0,adelay=45000|45000[m2];"
        "[m1][m2]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-23:TP=-3:LRA=9,volume=0.85[m];"
        f"[m][key]{duck}[duck];"
        "[v][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "[a]", "-ar", "48000", f"{OUT}/mix.wav")
    run("-i", f"{OUT}/picture.mp4", "-i", f"{OUT}/mix.wav", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", FINAL)
    print("SHORT DONE", FINAL, flush=True)
