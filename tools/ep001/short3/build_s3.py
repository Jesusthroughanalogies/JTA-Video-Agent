"""Ep 1 Short 3 v3: new standalone narration by Arthur, cut to approved Ep 1 shots."""
import json
import subprocess
import sys

sys.path.insert(0, "/tmp/cut")
import shorts as SH  # noqa: E402  (background, ass, constants)

G = "/tmp/cut/graded"
SEG = "/tmp/cut/v2/seg"
OUT = "/tmp/s3"
WORDS = json.load(open(f"{OUT}/words.json"))
VH = SH.VH


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def seg(sid):
    import glob
    return glob.glob(f"{SEG}/*_{sid}.mp4")[0]


# (start, end, source, kind, offset into source)
EDIT = [
    (0.0, 4.5, f"{G}/5f1988c1-7f8a-4a22-8174-8ebe75b9de4e.mp4", "ai", 0.3),     # villa, the fresco
    (4.5, 7.8, seg("P3-02"), "anim", None),                                      # brush paints the sunrise (end of shot)
    (7.8, 9.3, f"{G}/08b01d5e-06c8-4f41-a46a-47887f30ca36.mp4", "ai", 1.0),     # the world: islands
    (9.3, 10.4, f"{G}/170e420e-99fb-4c56-bf3d-e8f986e3305d.mp4", "ai", 1.5),    # the sunrise
    (10.4, 11.4, f"{G}/fa0e0ad5-a639-4f8e-be9a-3118411b1a5e.mp4", "ai", 1.5),   # the ocean
    (11.4, 12.75, f"{G}/b60a0d6b-a579-4c70-b1ea-d4bbaa7d0f0a.mp4", "ai", 1.5),  # the stars
    (12.75, 15.65, seg("P4-01"), "anim", 0.8),                                   # the world is God's painting
    (15.65, 18.6, f"{G}/732d976f-e900-4382-8e98-6e42fafa743d.mp4", "ai", 0.5),  # tells you about the one who made it
    (18.6, 23.1, f"{G}/7250e797-ad8e-456a-a282-b6467e403589.mp4", "ai", 0.3),   # never meet the painter
    (23.1, 26.05, seg("P4-03"), "anim", None),                                   # the painter steps into the painting
    (26.05, 29.25, f"{G}/941bab45-8687-476a-9c0b-cc4f4a9701a9.mp4", "ai", 0.5), # two thousand years ago
    (29.25, 33.2, f"{G}/cbc91c7b-4556-4b45-b215-8c5bdfcd4f6a.mp4", "ai", 0.6),  # God stepped into His own world. Jesus.
    (33.2, 36.7, f"{G}/a78815f4-7710-482d-b4c0-56366c3f06d2.mp4", "ai", 0.5),   # watch how He lived
    (36.7, 37.95, f"{G}/5ab69173-dcda-43a9-bd1c-a16a4aa58ea7.mp4", "ai", 1.8),  # He fed the poor
    (37.95, 40.2, f"{G}/1e15c5a7-7112-4e99-be77-2652528562b6.mp4", "ai", 1.0),  # touched the people nobody would touch
    (40.2, 42.6, f"{G}/91600f8a-c0e6-4916-b674-9e2ac5a5c4ef.mp4", "ai", 1.0),   # forgave the people who killed Him
    (42.6, 44.2, seg("P4-01"), "anim", 3.0),                                     # didn't just leave you His painting
    (44.2, 47.4, seg("P4-16"), "anim", None),                                    # He came looking for you
]
TOTAL = 47.4

if __name__ == "__main__":
    import os
    # grade the new bread clip if needed
    if not os.path.exists(f"{G}/5ab69173-dcda-43a9-bd1c-a16a4aa58ea7.mp4"):
        from jta_visuals.rules import GRADE_FILTER
        run("-i", "/tmp/cut/raw/5ab69173-dcda-43a9-bd1c-a16a4aa58ea7.mp4", "-vf",
            f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,{GRADE_FILTER}", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            f"{G}/5ab69173-dcda-43a9-bd1c-a16a4aa58ea7.mp4")
    parts = []
    for i, (a, b, src, kind, off) in enumerate(EDIT):
        d = b - a
        n = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                                 capture_output=True, text=True).stdout)
        if off is None:            # anim shots: use the end of the shot, where the action lands
            off = max(n - d, 0)
        slow = max(d / max(n - off, 0.1), 1.0)
        crop = "crop=1300:760:310:68" if kind == "anim" else "crop=1440:840:240:120"
        p = f"{OUT}/p{i:02d}.mp4"
        run("-ss", f"{off:.3f}", "-i", src, "-t", f"{min(d / slow, n - off):.3f}", "-vf",
            f"setpts={slow:.4f}*PTS,{crop},scale=1080:{VH},fps=30,tpad=stop_mode=clone:stop_duration=2",
            "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", p)
        parts.append(p)
    open(f"{OUT}/list.txt", "w").write("".join(f"file '{p}'\n" for p in parts))
    run("-f", "concat", "-safe", "0", "-i", f"{OUT}/list.txt", "-c", "copy", f"{OUT}/video.mp4")
    bg = f"{OUT}/bg.png"
    SH.background(bg, "THE PAINTER STEPPED", "INTO HIS PAINTING")
    words = [(w["text"], w["start"]) for w in WORDS]
    SH.ass(f"{OUT}/s3.ass", words, TOTAL)
    run("-i", f"{OUT}/video.mp4", "-loop", "1", "-i", bg, "-filter_complex",
        f"[1:v][0:v]overlay=0:{SH.VY}:shortest=1,ass={OUT}/s3.ass,format=yuv420p[ov]", "-map", "[ov]",
        "-t", f"{TOTAL:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", f"{OUT}/picture.mp4")
    print("picture done")
    if os.path.exists(f"{OUT}/vo.mp3") and os.path.getsize(f"{OUT}/vo.mp3") > 1000:
        # Ananda Yoga, timed so its lift lands on "Unless the painter steps into the painting" (23.1 s)
        run("-i", f"{OUT}/vo.mp3", "-i", "/tmp/music/Ananda Yoga.mp3", "-filter_complex",
            "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur=47.4,asplit=2[v][key];"
            "[1:a]atrim=start=31.9:duration=47.4,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
            "afade=t=in:d=1.5,afade=t=out:st=45.6:d=1.8,volume=0.42[m];"
            "[m][key]sidechaincompress=threshold=0.025:ratio=3.5:attack=40:release=500[duck];"
            "[v][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "[a]", "-ar", "48000", f"{OUT}/mix.wav")
        run("-i", f"{OUT}/picture.mp4", "-i", f"{OUT}/mix.wav", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", "/tmp/cut/shorts/JTA_Ep1_Short_03_the_painter.mp4")
        print("SHORT DONE")
