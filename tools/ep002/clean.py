"""Label-free 1080p master from the existing segments and transitions (no re-rendering)."""
import sys
sys.argv = ["x"]
src = open("/tmp/ep2/build.py").read().split('if __name__')[0]
exec(src)
import json
from concurrent.futures import ThreadPoolExecutor
P = json.load(open(CUT / "plan.json"))
slots = P["slots"]
segs = sorted(str(p) for p in SEG.glob("*.mp4"))
assert len(segs) == len(slots)
cut_in, cut_out, txs = {}, {}, {}
for k in range(len(slots) - 1):
    A, B = slots[k], slots[k + 1]
    if {A["kind"], B["kind"]} == {"live", "anim"} and A["dur"] >= 2.4 + (TX_B if k in cut_in else 0) and B["dur"] >= 2.6:
        cut_out[k] = TX_A; cut_in[k + 1] = TX_B; txs[k] = TX / f"{k:03d}.mp4"
OUT = CUT / "clean"; OUT.mkdir(exist_ok=True)
def piece(k):
    p = OUT / f"{k:03d}.mp4"
    if not p.exists():
        ss, to = cut_in.get(k, 0.0), slots[k]["dur"] - cut_out.get(k, 0.0)
        ff("-ss", f"{ss:.3f}", "-i", segs[k], "-t", f"{max(to - ss, 0.04):.3f}", "-vf", "fps=30", "-an", *ENC, str(p))
    return p
with ThreadPoolExecutor(2) as ex:
    ps = list(ex.map(piece, range(len(slots))))
lst = []
for k, p in enumerate(ps):
    lst.append(p)
    if k in txs:
        lst.append(txs[k])
(OUT / "list.txt").write_text("".join(f"file '{p}'\n" for p in lst))
ff("-f", "concat", "-safe", "0", "-i", str(OUT / "list.txt"), "-c", "copy", str(CUT / "video_clean.mp4"))
ff("-i", str(CUT / "video_clean.mp4"), "-i", "/tmp/ep2/cut/mix.wav", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
   "-shortest", "-movflags", "+faststart", "/tmp/ep2/JTA_Ep2_MASTER_1080p.mp4")
print("MASTER", dur("/tmp/ep2/JTA_Ep2_MASTER_1080p.mp4"))
