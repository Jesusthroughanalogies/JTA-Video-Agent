"""Ep 1 review cut v2: Arthur's voiceover, every shot timed to his words, paint-over transitions
between AI footage and animation, captions on the animations."""
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path("/home/claude/jta-video-agent")
sys.path.insert(0, str(REPO))
from episodes.ep001.shots import SHOTS  # noqa: E402
from jta_agent.pipeline import PREFIX_PART  # noqa: E402
from jta_agent.voice import parse_script, row_key  # noqa: E402
from jta_visuals.rules import GRADE_FILTER  # noqa: E402

CUT = Path("/tmp/cut/v2")
RAW, GRADED = Path("/tmp/cut/raw"), Path("/tmp/cut/graded")
SEG, TX, PIECE = CUT / "seg", CUT / "tx", CUT / "piece"
for d in (SEG, TX, PIECE):
    d.mkdir(parents=True, exist_ok=True)
VO = Path("/tmp/voice/vo")
ALIGN = json.load(open("/tmp/voice/align.json"))
FONT = str(REPO / "assets/fonts/IMFellDWPica-Regular.ttf")
ORDER = ["01_hook", "02_part1", "03_part2", "04_part3", "05_part4", "06_outro"]
PAUSE, PART_GAP = 1.6, 0.7
PAUSE_FOR = {"H-10": 2.6}   # Matt, 2 Nov: the title card holds 1 s longer
TX_A, TX_B = 1.25, 1.35          # how much of each neighbour the 2.6 s transition replaces
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p"]


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(p)], capture_output=True, text=True).stdout)


def kind(s):
    if s.tag == "AI":
        return "live"
    if s.tag == "TEXT" and s.background:
        return "card"
    return "anim"


def plan():
    """Rows in script order with real times from Arthur's read. Returns slots and the audio chunk list."""
    script = [l for l in parse_script(REPO / "episodes/ep001/script.md")
              if not (l.part == "01_hook" and l.row in ("06", "07"))]
    by_row = {}
    for s in SHOTS:
        pre, row = s.id.split("-", 1)
        by_row.setdefault((PREFIX_PART[pre], row_key(row)), []).append(s)
    slots, audio, t = [], [], 0.0
    for part in ORDER:
        lines = ALIGN[part]["lines"]
        spoken = [l for l in script if l.part == part and not l.text.startswith("(")]
        assert len(spoken) == len(lines), (part, len(spoken), len(lines))
        rows = sorted({k[1] for k in by_row if k[0] == part} | {l.row for l in script if l.part == part},
                      key=lambda r: (int("".join(c for c in r if c.isdigit())), r))
        li = 0
        pdur = dur(VO / f"{part}.mp3")
        groups = []   # (shots, [line indexes] or None for a pause)
        for r in rows:
            sc = next((l for l in script if l.part == part and l.row == r), None)
            idx = None
            if sc is not None and not sc.text.startswith("("):
                idx = li
                li += 1
            shots = by_row.get((part, r))
            if not shots:          # a spoken row with no shot of its own extends the previous row
                if idx is not None and groups:
                    groups[-1][1].append(idx)
                continue
            groups.append((shots, [idx] if idx is not None else []))
        for gi, (shots, idxs) in enumerate(groups):
            if not idxs:           # (pause) row: silence
                a0 = a1 = None
                d = max(PAUSE_FOR.get(s.id, PAUSE) for s in shots)
            else:
                a0 = 0.0 if idxs[0] == 0 else lines[idxs[0]]["start"] - 0.12
                nxt = next((g[1][0] for g in groups[gi + 1:] if g[1]), None)
                a1 = (lines[nxt]["start"] - 0.12) if nxt is not None else pdur
                d = a1 - a0
                if nxt is None:
                    d += PART_GAP
            words = [(w, round(tm - a0, 3)) for i in idxs for w, tm in lines[i]["words"]] if idxs else []
            audio.append((part, a0, a1, d))
            # an AI clip that is only a TEXT card's background is shown under the card, not on its own
            vis = [s for s in shots if not any(o.background == s.id for o in shots)] if len(idxs) <= 1 else shots
            if len(vis) == len(idxs) and len(vis) > 1:     # one shot per line
                bounds = [0.0] + [lines[i]["start"] - 0.12 - a0 for i in idxs[1:]] + [d]
            else:
                bounds = [d * k / len(vis) for k in range(len(vis) + 1)]
            for k, s in enumerate(vis):
                s0, s1 = bounds[k], bounds[k + 1]
                slots.append({"id": s.id, "tag": s.tag, "kind": kind(s), "start": t + s0, "dur": s1 - s0,
                              "reuse": s.reuse, "background": s.background,
                              "words": [(w, round(x - s0, 3)) for w, x in words if s0 - 0.05 <= x < s1]})
            t += d
    return slots, audio


def graded(job):
    out = GRADED / f"{job}.mp4"
    if not out.exists():
        ff("-i", str(RAW / f"{job}.mp4"), "-vf",
           f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,{GRADE_FILTER}", "-an", *ENC, str(out))
    return out


def boomerang(job):
    """The clip slowed slightly, then played forward and back, so long lines never freeze."""
    out = GRADED / f"{job}_boom.mp4"
    if not out.exists():
        ff("-i", str(graded(job)), "-filter_complex",
           "[0:v]setpts=1.25*PTS,fps=30,split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[o]", "-map", "[o]", *ENC, str(out))
    return out


def build(i_slot):
    i, sl = i_slot
    out = SEG / f"{i:03d}_{sl['id']}.mp4"
    if out.exists():
        return str(out)
    d = sl["dur"]
    shots = {s.id: s for s in SHOTS}
    if sl["tag"] == "AI":
        src = graded(sl["reuse"])
        n = dur(src)
        if d <= n * 1.3:
            f = max(d / n, 1.0)
            ff("-i", str(src), "-vf", f"setpts={f:.4f}*PTS,fps=30", "-t", f"{d:.3f}", "-an", *ENC, str(out))
        else:
            ff("-stream_loop", "-1", "-i", str(boomerang(sl["reuse"])), "-t", f"{d:.3f}", "-an", *ENC, str(out))
    else:
        from jta_anim.scenes_ep001 import render_shot
        bg = graded(shots[sl["background"]].reuse) if sl["background"] else None
        render_shot(sl["id"], d, out, words=sl["words"], bg_video=bg)
    return str(out)


def label(sid):
    return (f"drawbox=x=24:y=24:w=170:h=46:color=black@0.55:t=fill,"
            f"drawtext=fontfile={FONT}:text='{sid}':fontcolor=0xE9DCC0:fontsize=30:x=36:y=34")


def trim(src, ss, to, sid, out):
    ff("-ss", f"{ss:.3f}", "-i", str(src), "-t", f"{max(to - ss, 0.04):.3f}", "-vf", f"fps=30,{label(sid)}", "-an",
       *ENC, str(out))
    return out


def tx_job(args):
    k, a, b, to_anim = args
    from jta_anim.transitions import transition
    out = TX / f"{k:03d}.mp4"
    if not out.exists():
        live, anim = (a, b) if to_anim else (b, a)
        transition(Path(live), Path(anim), out, to_anim=to_anim)
    return str(out)


if __name__ == "__main__":
    slots, audio = plan()
    json.dump({"slots": slots, "audio": audio}, open(CUT / "plan.json", "w"), indent=1)
    print(len(slots), "shots,", round(sum(s["dur"] for s in slots) / 60, 2), "min", flush=True)
    for sl in slots:
        if sl["tag"] == "AI":
            graded(sl["reuse"])
    with ProcessPoolExecutor(2) as ex:
        segs = list(ex.map(build, enumerate(slots)))
    print("segments done", flush=True)
    # transitions between live footage and animation
    jobs, cut_in, cut_out = [], {}, {}
    for k in range(len(slots) - 1):
        A, B = slots[k], slots[k + 1]
        pair = {A["kind"], B["kind"]}
        if pair == {"live", "anim"} and A["dur"] >= 2.4 + (TX_B if k in cut_in else 0) and \
                B["dur"] >= 2.6:
            jobs.append((k, segs[k], segs[k + 1], A["kind"] == "live"))
            cut_out[k] = TX_A
            cut_in[k + 1] = TX_B
    with ProcessPoolExecutor(2) as ex:
        txs = dict(zip([j[0] for j in jobs], ex.map(tx_job, jobs)))
    print(len(txs), "transitions done", flush=True)
    pieces = []
    for k, sl in enumerate(slots):
        p = PIECE / f"{k:03d}.mp4"
        if not p.exists():
                trim(segs[k], cut_in.get(k, 0.0), sl["dur"] - cut_out.get(k, 0.0), sl["id"], p)
        pieces.append(p)
        if k in txs:
            q = PIECE / f"{k:03d}_tx.mp4"
            if not q.exists():
                ff("-i", txs[k], "-vf", label(f"{sl['id']}>"), "-an", *ENC, str(q))
            pieces.append(q)
    (CUT / "list.txt").write_text("".join(f"file '{p}'\n" for p in pieces))
    ff("-f", "concat", "-safe", "0", "-i", str(CUT / "list.txt"), "-c", "copy", str(CUT / "video.mp4"))
    # narration track
    chunks = []
    for j, (part, a0, a1, d) in enumerate(audio):
        c = CUT / f"a{j:03d}.wav"
        if a0 is None:
            ff("-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=44100:cl=stereo", str(c))
        else:
            ff("-ss", f"{max(a0, 0):.3f}", "-to", f"{a1:.3f}", "-i", str(VO / f"{part}.mp3"),
               "-af", f"apad=whole_dur={d:.3f}", "-ar", "44100", "-ac", "2", str(c))
        chunks.append(c)
    (CUT / "alist.txt").write_text("".join(f"file '{c}'\n" for c in chunks))
    ff("-f", "concat", "-safe", "0", "-i", str(CUT / "alist.txt"), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
       "-ar", "48000", str(CUT / "voice.wav"))
    ff("-i", str(CUT / "video.mp4"), "-i", str(CUT / "voice.wav"), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
       "-shortest", "-movflags", "+faststart", "/tmp/cut/JTA_Ep1_review_cut_v2.mp4")
    print("video", dur(CUT / "video.mp4"), "voice", dur(CUT / "voice.wav"), flush=True)
    print("DONE", flush=True)
