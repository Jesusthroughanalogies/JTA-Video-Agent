"""The 8-phase pipeline. Resumes from the last saved step on every start.

Each phase is a list of steps. A step is recorded done only after its output
is on disk, so a restart skips finished steps and redoes at most the one that
was interrupted. Checkpoints A to D are gates: the next phase does not start
until a human runs `jta approve <episode> <checkpoint>` (dry runs approve
themselves). Credits are never spent before Checkpoint C.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from jta_visuals.plan import load_shots

from . import llm, media
from . import state as S
from .config import REPO, Paths, Settings
from .dryrun import FakeBackend, fake_qc
from .generate import Generator, load_plan
from .higgsfield import Backend
from .ledger import Ledger
from .runtime import Blocked, Control, Log, NeedsApproval, Paused
from .state import CHECKPOINT_AFTER, PHASES, EpisodeState
from .voice import FakeVoice, VoiceBackend, generate_voiceover, parse_script, row_key

GATE_BEFORE = {PHASES[PHASES.index(p) + 1]: cp for p, cp in CHECKPOINT_AFTER.items()}
PREFIX_PART = {"H": "01_hook", "P1": "02_part1", "P2": "03_part2", "P3": "04_part3",
               "P4": "05_part4", "O": "06_outro", "ST": "story"}
PART_TITLES = {"01_hook": "Intro", "02_part1": "Picture 1: the dominoes", "03_part2": "Picture 2: the dials",
               "04_part3": "Picture 3: the painting", "story": "Our story",
               "05_part4": "The painter steps into the painting", "06_outro": "What's next"}
NIV_LINE = ("Scripture quotations taken from The Holy Bible, New International Version® NIV®. "
            "Copyright © 1973, 1978, 1984, 2011 by Biblica, Inc.™ Used by permission. "
            "All rights reserved worldwide.")
VOICE_DISCLOSURE = ("Narration uses AI voice clones of Matt and Jack's own voices, made with their consent. "
                    "The personal story is recorded live.")  # Section 6.3, verbatim
RECORDED_DISCLOSURE = "Narration is recorded by Matt and Jack in their own voices."  # NARRATION = "recorded"
STORY_FILES = ("story.wav", "story.mp3", "story.m4a")
AUDIO_EXTS = (".wav", ".mp3", ".m4a")
VOICE_PARTS = ["01_hook", "02_part1", "03_part2", "04_part3", "05_part4", "06_outro"]


def episode_meta(shots_path: Path) -> dict:
    """Per-episode settings declared in shots.py.

    NARRATION = "clones" (default): the voiceover is generated from the ElevenLabs clones (Section 6.2).
    NARRATION = "recorded": Matt and Jack record the whole voiceover themselves (one file per part,
    or one per part per speaker) and the clones are not used. Ep 1 works this way.
    The personal story is included only when the shot list has ST- shots.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("episode_meta_shots", shots_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    narration = getattr(mod, "NARRATION", "clones")
    if narration not in ("clones", "recorded"):
        raise ValueError(f"NARRATION must be 'clones' or 'recorded', not {narration!r}")
    return {"narration": narration, "story": any(sh.id.startswith("ST-") for sh in mod.SHOTS)}


def recorded_files(inputs: Path, part: str) -> list[Path]:
    """The recorded voiceover for one part: 02_part1.wav, or 02_part1_matt.wav + 02_part1_jack.wav."""
    for ext in AUDIO_EXTS:
        if (inputs / f"{part}{ext}").exists():
            return [inputs / f"{part}{ext}"]
    return sorted(f for f in inputs.glob(f"{part}_*") if f.suffix in AUDIO_EXTS)


class Pipeline:
    def __init__(self, paths: Paths, cfg: Settings, st: EpisodeState, backend: Backend,
                 voice: VoiceBackend, control: Control, log: Log):
        self.p, self.cfg, self.st, self.hf, self.voice = paths, cfg, st, backend, voice
        self.control, self.log = control, log
        self.ledger = Ledger(paths.ledger, cfg.credit_cap)
        self.size = "426x240" if paths.dry_run else "1280x720"
        self.final_size = "426x240" if paths.dry_run else "1920x1080"
        self.meta = episode_meta(paths.shots) if paths.shots.exists() else {"narration": "clones", "story": True}
        if self.meta["narration"] == "recorded":
            self.disclosure = RECORDED_DISCLOSURE
        elif self.meta["story"]:
            self.disclosure = VOICE_DISCLOSURE
        else:  # no live story this episode, so don't claim one (Section 6.3 line, first sentence only)
            self.disclosure = VOICE_DISCLOSURE.split(" The personal story")[0]

    # ------------------------------------------------------------------ driver
    def run(self) -> None:
        while self.st.phase != "finished":
            phase = self.st.phase
            self.control.check()
            cp = GATE_BEFORE.get(phase)
            if cp and not self.st.checkpoint(cp)["approved"]:
                if self.cfg.auto_approve:
                    self.st.approve(cp, by="dry-run (auto)")
                    self.log("checkpoint", f"{cp} auto-approved (dry run)")
                else:
                    msg = self._checkpoint_message(cp)
                    self.st.set_status("awaiting_approval", f"checkpoint {cp}")
                    raise NeedsApproval(msg)
            self.st.data["status"] = "running"
            self.st.save()
            self.log("phase", f"{PHASES.index(phase) + 1}/8 {phase}")
            getattr(self, f"phase_{phase}")()
            self.st.finish_phase(phase)
            if self.cfg.until == phase:
                raise Paused(f"stopped after {phase} as asked (--until {phase})")
        self.st.set_status("done", "all phases finished")
        self.log("finished", f"{self.st.data['episode_id']} complete")

    def step(self, phase: str, name: str, fn: Callable[[], dict | None]) -> None:
        if self.st.step_done(phase, name):
            return
        self.control.check()
        info = fn() or {}
        self.st.mark_step(phase, name, **info)
        self.log("step", f"{phase}.{name} done")

    def agent(self, task: str, expect: list[Path], stub: Callable[[], None]) -> None:
        """A Claude step in live mode; a deterministic stand-in in dry runs."""
        if self.cfg.use_llm:
            llm.run_step(task, expect)
        else:
            stub()

    # ------------------------------------------------------------------ 1 topic, 2 script
    def phase_topic(self) -> None:
        out = self.p.work / "topic.md"
        self.step("topic", "propose", lambda: self.agent(
            f"Phase 1 for episode {self.p.episode}. Write the topic proposal for Checkpoint A to {out}.",
            [out], lambda: _write(out, "# Topic (dry run)\n\nPlaceholder proposal.\n")))

    def phase_script(self) -> None:
        out = self.p.ep_dir / "script.md" if not self.p.dry_run else self.p.work / "script.md"
        if not self.p.dry_run and out.exists():
            self.step("script", "write", lambda: {"note": "script.md already in the repo"})
            return
        src = self.p.ep_dir / "script.md"
        self.step("script", "write", lambda: self.agent(
            f"Phase 2 for episode {self.p.episode}. Using the approved topic in {self.p.work / 'topic.md'}, "
            f"write the full AV script to {out} (markdown tables `# | Words | Visual`, **MATT:**/**JACK:** "
            f"speaker tags, a '## Personal story' section with prompts only).",
            [out], lambda: shutil.copyfile(src, out) if src.exists() else _write(out, "# empty\n")))

    def script_path(self) -> Path:
        dry = self.p.work / "script.md"
        return dry if self.p.dry_run and dry.exists() else self.p.ep_dir / "script.md"

    # ------------------------------------------------------------------ 3 voiceover, ingest, align
    def phase_ingest(self) -> None:
        voice_dir = self.p.media / "voice"
        inputs = self.p.media / "inputs"
        timeline = self.p.work / "timeline.json"

        recorded = self.meta["narration"] == "recorded"

        def voiceover() -> dict:
            if recorded:
                return {"note": "NARRATION = recorded: Matt and Jack's own recordings are used, no clones"}
            parts = generate_voiceover(self.st, self.script_path(), voice_dir, self.voice, self.log,
                                       char_cap=_voice_cap(), control_check=self.control.check)
            return {"parts": {k: len(v) for k, v in parts.items()}}
        self.step("ingest", "voiceover", voiceover)

        def pull_inputs() -> dict:
            if not self.cfg.use_llm:
                _fake_inputs(inputs, self.meta)
            else:
                llm.run_step(
                    f"Download every file in Google Drive /JTA/Episodes/{self.st.data['episode_id']}/inputs/ "
                    f"into {inputs}/ keeping the file names. Then list what you saved.", [])
            missing = _missing_inputs(inputs, self.meta)
            if missing:
                raise Blocked("waiting for these files in the Drive inputs folder: " + ", ".join(missing))
            return {"files": sorted(f.name for f in inputs.iterdir())}
        self.step("ingest", "inputs", pull_inputs)

        def align() -> dict:
            for round_ in range(1, 3):
                if self.cfg.use_llm:
                    llm.run_step(
                        f"Phase 3 steps 3 to 5. Transcribe "
                        + (f"the recorded voiceover files in {inputs} (01_hook to 06_outro)" if recorded
                           else f"every file in {voice_dir}" + (f" and the live story in {inputs}" if self.meta["story"] else ""))
                        + " "
                        f"with word timestamps, align to {self.script_path()} and the shots in {self.p.shots}, and "
                        f"write {timeline} with keys: slots [{{shot,start,end}}] covering every shot in order, "
                        f"audio [ordered audio file paths], words [{{w,start,end}}], deviations [..], and "
                        f"voice_issues [{{line, reason}}] for any cloned line with wrong stress, an odd pause or a "
                        f"mispronounced name (Section 6.2).", [timeline])
                else:
                    _write(timeline, json.dumps(self._dry_timeline(voice_dir, inputs), indent=1))
                issues = json.loads(timeline.read_text()).get("voice_issues", [])
                if recorded:
                    return {"round": round_, "note": "recorded narration: flagged lines go to the humans, not regenerated",
                            "voice_issues": issues}
                if not issues:
                    return {"round": round_}
                redo = {i["line"] for i in issues}
                self.log("voice-redo", f"regenerating {len(redo)} line(s): {', '.join(sorted(redo))}")
                generate_voiceover(self.st, self.script_path(), voice_dir, self.voice, self.log,
                                   char_cap=_voice_cap(), control_check=self.control.check, redo=redo)
                timeline.unlink()
            raise Blocked(f"voice lines still flagged after 2 rounds: {issues}")
        self.step("ingest", "align", align)

    def _dry_timeline(self, voice_dir: Path, inputs: Path) -> dict:
        """Deterministic stand-in for alignment: each script row lasts as long as its voice line."""
        lines = {(l.part, l.row): l for l in parse_script(self.script_path())}
        _, shots = load_shots(self.p.shots)
        gap = 0.25
        audio, slots, words, t = [], [], [], 0.0
        story = next((inputs / f for f in STORY_FILES if (inputs / f).exists()), None)
        order = ["01_hook", "02_part1", "03_part2", "04_part3", "story", "05_part4", "06_outro"]
        recorded = self.meta["narration"] == "recorded"
        # Recorded narration: each part's audio is shared out across its rows by word count.
        rec_share: dict[tuple, tuple] = {}
        if recorded:
            for part in VOICE_PARTS:
                files = recorded_files(inputs, part)
                if not files:
                    continue
                total = sum(media.duration(f) for f in files)
                # every row with a shot gets a share; rows with no spoken line (a pause) count as 4 words
                rows = sorted({row_key(sh.id.split("-", 1)[1]) for sh in shots
                               if PREFIX_PART[sh.id.split("-", 1)[0]] == part})
                wc = {row: max(1, len(lines[(part, row)].text.split())) if (part, row) in lines else 4
                      for row in rows}
                for row in rows:
                    rec_share[(part, row)] = (files[0], total * wc[row] / sum(wc.values()))
        by_part: dict[str, list] = {}
        for s in shots:
            pre, row = s.id.split("-", 1)
            by_part.setdefault(PREFIX_PART[pre], []).append((row_key(row), s))
        for part in order:
            rows: dict[int, list] = {}
            for row, s in by_part.get(part, []):
                rows.setdefault(row, []).append(s)
            for row in sorted(rows):
                if part == "story":
                    f = story
                    dur = media.duration(f)
                elif recorded:
                    f, dur = rec_share.get((part, row), (None, 2.0))
                else:
                    ln = lines.get((part, row))
                    f = voice_dir / part / f"{row}_{ln.speaker.lower()}{self.voice.ext}" if ln else None
                    dur = (media.duration(f) + gap) if f else 2.0
                if f and recorded and part != "story":
                    if not audio or audio[-1] != str(f):
                        audio.append(str(f))  # one file per part, added once
                    text = lines[(part, row)].text if (part, row) in lines else ""
                    ws = text.split()
                    for i, w in enumerate(ws):
                        words.append({"w": w, "start": round(t + i * dur / len(ws), 2),
                                      "end": round(t + (i + 1) * dur / len(ws), 2)})
                elif f:
                    audio.append(str(f))
                    text = lines[(part, row)].text if part != "story" else "(live story)"
                    ws = text.split()
                    for i, w in enumerate(ws):
                        words.append({"w": w, "start": round(t + i * dur / len(ws), 2),
                                      "end": round(t + (i + 1) * dur / len(ws), 2)})
                else:
                    audio.append(f"silence:{dur}")
                group = [s for s in rows[row] if not any(o.background == s.id for o in rows[row])]
                for i, s in enumerate(group):
                    slots.append({"shot": s.id, "start": round(t + i * dur / len(group), 3),
                                  "end": round(t + (i + 1) * dur / len(group), 3)})
                t += dur
        return {"slots": slots, "audio": audio, "words": words, "deviations": [], "voice_issues": []}

    # ------------------------------------------------------------------ 4 shot list, 5 generate
    def phase_shotlist(self) -> None:
        def write_shots() -> dict:
            if self.p.shots.exists():
                return {"note": "shots.py already written"}
            self.agent(f"Phase 4 step 1: write {self.p.shots} for this episode.", [self.p.shots], lambda: None)
            return {}
        self.step("shotlist", "shots", write_shots)

        def plan() -> dict:
            r = subprocess.run([sys.executable, "-m", "jta_visuals.plan", str(self.p.shots.relative_to(REPO))],
                               cwd=REPO, capture_output=True, text=True)
            (self.p.work).mkdir(parents=True, exist_ok=True)
            (self.p.work / "plan_output.txt").write_text(r.stdout + r.stderr)
            self.log("plan", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")
            if r.returncode != 0:
                raise Blocked("the planner rejected the shot list:\n" + r.stdout[-1500:])
            p = load_plan(self.p.plan)
            return {"steps": len(p["steps"]), "credits_with_redos": p["credits_with_redos"]}
        self.step("shotlist", "plan", plan)

    def phase_generate(self) -> None:
        if not self.p.dry_run and not self.st.checkpoint("C")["approved"]:
            raise NeedsApproval("Checkpoint C (spend) is not approved; no credits will be spent.")
        steps = {s["key"]: s for s in load_plan(self.p.plan)["steps"]}
        _, shots = load_shots(self.p.shots)
        words = {s.id: s.words for s in shots}

        def qc(key: str, step: dict, file: Path, job_id: str) -> tuple[bool, str]:
            if not self.cfg.use_llm:
                return fake_qc(job_id)
            frames = media.qc_frames(file, self.p.work / "qc" / key)
            return llm.qc_clip(key, step, frames, words.get(key.rsplit("-v", 1)[0].removesuffix("-frame"), ""))

        Generator(self.p, self.st, self.ledger, self.hf, qc, self.control, self.log, self.cfg).run()
        fb = self.st.jobs_with(S.FALLBACK)
        if fb:
            self.log("fallback", f"{len(fb)} AI shot(s) need an animation instead: {', '.join(fb)}")

    # ------------------------------------------------------------------ 6 assemble, 7 package
    def _shot_sources(self) -> dict[str, Path]:
        """Best file per shot id: graded AI clip (v1 if kept, else v2), reused clip, or a card."""
        _, shots = load_shots(self.p.shots)
        tl = json.loads((self.p.work / "timeline.json").read_text())
        dur = {s["shot"]: s["end"] - s["start"] for s in tl["slots"]}
        inputs = self.p.media / "inputs"
        src: dict[str, Path] = {}
        for s in shots:
            seconds = max(dur.get(s.id, 3.0), 0.5)
            if s.tag == "AI":
                f = self._ai_file(s.id, s.reuse)
                if f:
                    src[s.id] = media.grade(f, self.p.media / "graded" / f"{s.id}.mp4")
                    continue
            if s.tag == "CLIP":
                name = "clip_intro.mp4" if s.id.startswith("H") else "clip_outro.mp4"
                if (inputs / name).exists():
                    src[s.id] = inputs / name
                    continue
            if s.tag == "PHOTO":
                photos = sorted(inputs.glob("story_*"))
                if photos:
                    src[s.id] = photos[0]
                    continue
            bg = None
            if s.tag == "TEXT" and s.background:
                bg = self._ai_file(s.background, None)
                bg = media.grade(bg, self.p.media / "graded" / f"{s.background}.mp4") if bg else None
            label = s.spec if s.tag == "TEXT" else f"[{s.tag}] {s.id}"
            src[s.id] = media.card(label[:60], self.p.media / "cards" / f"{s.id}.mp4", seconds, self.size, bg)
        return src

    def _ai_file(self, shot_id: str, reuse: str | None) -> Path | None:
        if reuse:
            dest = self.p.media / "reused" / f"{shot_id}.mp4"
            if not media.done(dest):
                url = self._reuse_url(reuse)
                self.hf.download(url, dest)
            return dest
        for v in (1, 2):
            j = self.st.data["jobs"].get(f"{shot_id}-v{v}")
            if j and j["status"] == S.DONE and j.get("file"):
                return self.p.base / j["file"]
        return None

    def _reuse_url(self, job_id: str) -> str:
        st = self.hf.wait([job_id], timeout=0).get(job_id)
        if self.p.dry_run:
            return f"fake://{job_id}.mp4"
        if not st or not st.result_url:
            raise Blocked(f"reused clip {job_id} has no result url")
        return st.result_url

    def _render(self, size: str, out: Path) -> Path:
        tl = json.loads((self.p.work / "timeline.json").read_text())
        src = self._shot_sources()
        segs = []
        for i, sl in enumerate(tl["slots"]):
            seconds = max(sl["end"] - sl["start"], 0.2)
            segs.append(media.segment(src[sl["shot"]], seconds,
                                      self.p.media / f"seg_{size}" / f"{i:03d}_{sl['shot']}.mp4", size))
            self.control.check()
        audio_files = []
        for a in tl["audio"]:
            if a.startswith("silence:"):
                secs = float(a.split(":")[1])
                audio_files.append(_silence(self.p.media / "silence", secs))
            else:
                audio_files.append(Path(a))
        narration = media.concat_audio(audio_files, self.p.media / "narration.wav")
        return media.render_cut(segs, narration, out)

    def phase_assemble(self) -> None:
        def anims() -> dict:
            if self.cfg.use_llm:
                llm.run_step(f"Phase 6 prep: render every [ANIM] and [TEXT] shot in {self.p.shots} to "
                             f"{self.p.media / 'cards'}/<shot id>.mp4 at 1920x1080, 30 fps, navy and gold "
                             f"(style bible). Durations from {self.p.work / 'timeline.json'}.", [])
            return {}
        self.step("assemble", "animations", anims)
        rough = self.p.media / "review" / "rough_cut.mp4"
        self.step("assemble", "rough_cut", lambda: {"file": str(self._render(self.size, rough)),
                                                    "seconds": round(media.duration(rough), 1)})

        def upload() -> dict:
            if self.cfg.use_llm:
                llm.run_step(f"Upload {rough} to Google Drive /JTA/Episodes/{self.st.data['episode_id']}/review/ "
                             f"and reply with the link.", [])
            return {}
        self.step("assemble", "upload_review", upload)

    def phase_package(self) -> None:
        final_dir = self.p.media / "final"
        final = final_dir / "final.mp4"
        self.step("package", "final_render", lambda: {"file": str(self._render(self.final_size, final))})
        self.step("package", "captions", lambda: {"file": str(self._srt(final_dir / "captions.srt"))})

        def upload_md() -> dict:
            out = final_dir / "upload.md"
            if self.cfg.use_llm:
                llm.run_step(
                    f"Phase 7 steps 2, 3 and 6. Write {out}: title, description, tags, pinned comment and 3 Shorts "
                    f"moments, plus one thumbnail in {final_dir}. The description must include these two lines "
                    f"exactly:\n{self.disclosure}\n{NIV_LINE}\nChapters:\n{self._chapters()}", [out])
                text = out.read_text()
                if self.disclosure not in text or NIV_LINE not in text:
                    raise Blocked("upload.md is missing the voice disclosure or the NIV line")
            else:
                _write(out, self._dry_upload_md())
            return {"file": str(out)}
        self.step("package", "upload_pack", upload_md)

    def _chapters(self) -> str:
        tl = json.loads((self.p.work / "timeline.json").read_text())
        seen, out = set(), []
        for sl in tl["slots"]:
            part = PREFIX_PART[sl["shot"].split("-")[0]]
            if part not in seen:
                seen.add(part)
                m, s = divmod(int(sl["start"] if out else 0), 60)
                out.append(f"{m}:{s:02d} {PART_TITLES[part]}")
        return "\n".join(out)

    def _srt(self, out: Path) -> Path:
        words = json.loads((self.p.work / "timeline.json").read_text())["words"]

        def ts(x: float) -> str:
            h, r = divmod(x, 3600)
            m, s = divmod(r, 60)
            return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"
        blocks, n = [], 1
        for i in range(0, len(words), 8):
            grp = words[i:i + 8]
            blocks.append(f"{n}\n{ts(grp[0]['start'])} --> {ts(grp[-1]['end'])}\n{' '.join(w['w'] for w in grp)}\n")
            n += 1
        _write(out, "\n".join(blocks))
        return out

    def _dry_upload_md(self) -> str:
        return (f"# Upload pack (dry run)\n\nTitle: Is There a God? 3 Pictures That Explain It\n\n"
                f"## Description\n\n(summary)\n\nChapters:\n{self._chapters()}\n\n{self.disclosure}\n\n"
                f"{NIV_LINE}\n\n## Checklist\n\n- [ ] private\n- [ ] not made for kids\n"
                f"- [ ] altered or synthetic content: ON\n- [ ] thumbnail\n- [ ] captions.srt\n")

    # ------------------------------------------------------------------ 8 learn
    def phase_learn(self) -> None:
        def write() -> dict:
            t = self.ledger.totals()
            jobs = self.st.data["jobs"].values()
            attempts = sum(len([a for a in j["attempts"] if a["status"] != "void"]) for j in jobs)
            rejects = sum(1 for j in jobs for a in j["attempts"] if a.get("qc") and not a["qc"]["keep"])
            if self.cfg.use_llm and not self.p.dry_run:
                llm.run_step(f"Phase 8 steps 1 and 2 for {self.st.data['episode_id']}. Ledger totals: {t}. "
                             f"State: {self.p.state}. Events: {self.p.events}.", [])
            else:
                _write(self.p.work / "learn.md",
                       f"# Run summary\n\ncredits spent: {t['spent']} of {t['cap']}\n"
                       f"generations: {attempts} attempts for {len(self.st.data['jobs'])} planned jobs, "
                       f"{rejects} QC rejects\n")
            return {"credits_spent": t["spent"], "attempts": attempts, "qc_rejects": rejects}
        self.step("learn", "episode_file", write)

    # ------------------------------------------------------------------ messages
    def _checkpoint_message(self, cp: str) -> str:
        ep = self.p.episode
        if cp == "C":
            out = (self.p.work / "plan_output.txt").read_text() if (self.p.work / "plan_output.txt").exists() else ""
            return (f"CHECKPOINT C: approve spend for {ep}?\n{out.strip()}\n"
                    f"Hero prompts: {self.p.plan}\nApprove with: jta approve {ep} C")
        what = {"A": "topic", "B": "script", "D": "rough cut"}[cp]
        where = {"A": self.p.work / "topic.md", "B": self.script_path(),
                 "D": self.p.media / "review" / "rough_cut.mp4"}[cp]
        return f"CHECKPOINT {cp}: approve the {what} for {ep}? See {where}\nApprove with: jta approve {ep} {cp}"


# ---------------------------------------------------------------------- helpers
def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".part")
    tmp.write_text(text)
    tmp.replace(p)


def _silence(d: Path, secs: float) -> Path:
    out = d / f"{secs:.2f}.wav"
    if not media.done(out):
        media._ff(out, ["-f", "lavfi", "-t", f"{secs:.2f}", "-i", "anullsrc=r=44100:cl=mono"])
    return out


def _voice_cap() -> int:
    import os
    return int(os.environ.get("JTA_VOICE_CHAR_CAP", 25000))


def _missing_inputs(d: Path, meta: dict | None = None) -> list[str]:
    meta = meta or {"narration": "clones", "story": True}
    need = []
    if meta["story"] and not any((d / f).exists() for f in STORY_FILES):
        need.append("story.wav (the live personal story)")
    if meta["narration"] == "recorded":
        need += [f"{p}.wav (or {p}_matt.wav + {p}_jack.wav)" for p in VOICE_PARTS if not recorded_files(d, p)]
    for f in ("clip_intro.mp4", "clip_outro.mp4"):
        if not (d / f).exists():
            need.append(f)
    if not list(d.glob("story_*")):
        need.append("story_01.jpg (photos, in story order)")
    return need


def _fake_inputs(d: Path, meta: dict | None = None) -> None:
    meta = meta or {"narration": "clones", "story": True}
    d.mkdir(parents=True, exist_ok=True)
    if meta["story"]:
        media.tone(20.0, d / "story.wav", freq=330)
    if meta["narration"] == "recorded":
        for i, p in enumerate(VOICE_PARTS):
            if not recorded_files(d, p):
                media.tone(20.0 if p not in ("01_hook", "06_outro") else 8.0, d / f"{p}.wav", freq=220 + 20 * i)
    for name in ("clip_intro.mp4", "clip_outro.mp4"):
        if not media.done(d / name):
            media._ff(d / name, ["-f", "lavfi", "-t", "5", "-i", "testsrc2=s=426x240:r=30",
                                 "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast"])
    if not media.done(d / "story_01.jpg"):
        media._ff(d / "story_01.jpg", ["-f", "lavfi", "-i", "color=c=0xE8B04B:s=640x360", "-frames:v", "1"])


def make_backends(paths: Paths) -> tuple[Backend, VoiceBackend]:
    if paths.dry_run:
        return FakeBackend(paths.base), FakeVoice()
    from .higgsfield import McpBackend
    from .voice import ElevenLabsTTS
    return McpBackend(), ElevenLabsTTS()
