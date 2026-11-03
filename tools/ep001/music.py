"""Ep 1 music bed from the Epidemic library cue map, crossfaded, ducked under Arthur's voice."""
import subprocess
import sys
SHIFT_AFTER, SHIFT = 36.0, 1.0   # H-10 held 1 s longer

M = "/tmp/music"
END = 537.0
X = 1.5  # crossfade seconds
# (start, end, track, offset into track)
CUES = [
    (0.0, 37.4, "Light and Dew", 19),      # weight change lands on the IS THERE A GOD? title
    (37.4, 108.1, "Icy Road", 0),          # dominoes, cause, the universe began
    (108.1, 114.0, "Epic Mirage", 113),    # higher voices under Genesis 1:1
    (114.0, 158.9, "Icy Road", 70.7),      # who made God, the quantum vacuum
    (158.9, 168.5, "Light and Dew", 60),   # picture one complete
    (168.5, 198.2, "The Old Book", 0),     # the dark chamber: no stars, no life
    (199.8, 237.8, "Light and Dew", 70),   # (silence on the pause) Hoyle and carbon
    (237.8, 247.3, "Epic Mirage", 215),    # Milky Way, Psalm 19:1
    (247.3, 295.5, "Icy Road", 10),        # archers, multiverse, weigh it up
    (295.5, 324.3, "Light and Dew", 108),  # picture two complete, the villa painting
    (324.3, 348.3, "Epic Mirage", 120),    # sunrise, Romans 1:20, something inside us
    (348.3, 409.1, "A Silent Regret", 20), # conscience, cruelty, betrayal
    (409.1, 419.0, "Light and Dew", 140),  # three pictures resolve
    (419.0, 483.5, "Ananda Yoga", 34),     # the painter steps in; lift on "the Word became flesh"
    (483.5, 504.0, "A Silent Regret", 85), # the crosses, read John, pray
    (504.0, 514.4, "Ananda Yoga", 180),    # peak: "He came looking for you"
    (514.4, 527.2, "Light and Dew", 30),   # subscribe, share
    (527.2, END, "The Old Book", 60),      # next week: suffering
]


def run(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


CUES = [(s + (SHIFT if s > SHIFT_AFTER else 0), e + (SHIFT if e > SHIFT_AFTER else 0), tr, off) for s, e, tr, off in CUES]
END += SHIFT
inputs, filters, labels = [], [], []
for i, (s, e, track, off) in enumerate(CUES):
    hard_in = i == 0 or CUES[i - 1][1] < s - 0.1      # after silence: plain fade-in
    lead = 0.0 if i == 0 else X / 2
    tail = X / 2 if i < len(CUES) - 1 and CUES[i + 1][0] <= e + 0.1 else 1.2
    t0, d = s - lead, (e - s) + lead + (tail if tail == X / 2 else 0)
    inputs += ["-i", f"{M}/{track}.mp3"]
    fin = 2.0 if i == 0 else (1.0 if hard_in else X)
    fout = X if tail == X / 2 else 1.2
    filters.append(f"[{i}:a]atrim=start={max(off - lead, 0):.3f}:duration={d:.3f},asetpts=PTS-STARTPTS,"
                   f"aformat=sample_rates=48000:channel_layouts=stereo,"
                   f"afade=t=in:d={fin}:curve=qsin,afade=t=out:st={max(d - fout, 0):.3f}:d={fout}:curve=qsin,"
                   f"adelay={int(t0 * 1000)}|{int(t0 * 1000)}[m{i}]")
    labels.append(f"[m{i}]")
filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,atrim=duration={END},"
               f"loudnorm=I=-23:TP=-3:LRA=9[bed]")
run(*inputs, "-filter_complex", ";".join(filters), "-map", "[bed]", "-ar", "48000", "/tmp/cut/music_bed.wav")

# duck under the voice, then mix and master for YouTube (-14 LUFS)
voice = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cut/v2/voice.wav"
run("-i", "/tmp/cut/music_bed.wav", "-i", voice, "-filter_complex",
    "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v][key];"
    "[0:a]volume=0.85[mb];"
    "[mb][key]sidechaincompress=threshold=0.025:ratio=3.5:attack=40:release=500:makeup=1[duck];"
    "[v][duck]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-14:TP=-1.5:LRA=11[out]",
    "-map", "[out]", "-ar", "48000", "/tmp/cut/mix.wav")
print("music mixed")
