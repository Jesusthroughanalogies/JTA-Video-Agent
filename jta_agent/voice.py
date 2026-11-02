"""Phase 3 step 1: narration from the ElevenLabs voice clones (Section 6).

Rules enforced in code, not left to the model:
- Only lines from the approved script (episodes/<id>/script.md) are voiced.
- MATT lines use MATT_VOICE_ID, JACK lines use JACK_VOICE_ID (from .env, never in code).
- The personal story is never voiced by a clone: that section is skipped and a
  line from it raises an error.
- Each line is saved the moment it's generated. On restart, finished lines are
  skipped; a line is redone only if its script text changed or QC flagged it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from . import media
from .state import EpisodeState, now
from .runtime import Blocked, Log, NeedsCredits

STORY_SECTION = re.compile(r"personal story", re.I)
PART_SECTION = re.compile(r"^(hook|part \d+|outro)\b", re.I)
SPEAKER = re.compile(r"^\*\*(MATT|JACK)( or (MATT|JACK))?:\*\*\s*", re.I)
STAGE = re.compile(r"\*\([^)]*\)\*|\([^)]*\)")  # *(music: ...)* and (pause) cues are not spoken
MAX_VOICE_ATTEMPTS = 3


@dataclass
class Line:
    key: str        # "02_part1-07"
    part: str       # "02_part1" (file naming from the kit README)
    row: int
    speaker: str    # "MATT" | "JACK"
    text: str

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(f"{self.speaker}|{self.text}".encode()).hexdigest()[:12]


def _part_slug(n: int, title: str) -> str:
    t = title.lower()
    if t.startswith("hook"):
        return f"{n:02d}_hook"
    if t.startswith("outro"):
        return f"{n:02d}_outro"
    m = re.match(r"part (\d+)", t)
    return f"{n:02d}_part{m.group(1)}" if m else f"{n:02d}_{re.sub(r'[^a-z0-9]+', '', t)[:12]}"


def parse_script(path: Path) -> list[Line]:
    """Spoken lines from the AV tables, with the speaker carried down until it changes."""
    lines: list[Line] = []
    section: Optional[str] = None
    part_no = 0
    speaker: Optional[str] = None
    for raw in path.read_text().splitlines():
        if raw.startswith("## "):
            title = raw[3:].strip()
            if STORY_SECTION.search(title):
                section, speaker = "story", None
            elif PART_SECTION.match(title):
                part_no += 1
                section, speaker = _part_slug(part_no, title), None
            else:
                section = None
            continue
        if section is None or section == "story" or not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        words = cells[1]
        m = SPEAKER.match(words)
        if m:
            if m.group(2):
                raise ValueError(f"{section} row {cells[0]}: 'MATT or JACK' lines are live recordings, not clones")
            speaker = m.group(1).upper()
            words = words[m.end():]
        text = STAGE.sub("", words).replace("**", "").replace("*", "").strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        if speaker is None:
            raise ValueError(f"{section} row {cells[0]}: no speaker before this line")
        lines.append(Line(f"{section}-{int(cells[0]):02d}", section, int(cells[0]), speaker, text))
    return lines


class VoiceBackend(Protocol):
    ext: str
    def speak(self, voice: str, text: str, dest: Path) -> int: ...  # returns characters billed


class ElevenLabsTTS:
    """ElevenLabs text-to-speech REST API.

    Settings follow Section 6.2 (natural, least dramatic). Override them in
    .env if a first listen says otherwise. Not yet run against the live API
    from this repo: check the first part by ear.
    """
    ext = ".mp3"

    def __init__(self):
        self.key = os.environ.get("ELEVENLABS_API_KEY", "")
        self.voices = {"MATT": os.environ.get("MATT_VOICE_ID", ""), "JACK": os.environ.get("JACK_VOICE_ID", "")}
        self.model = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
        self.settings = {
            "stability": float(os.environ.get("ELEVENLABS_STABILITY", 0.5)),
            "similarity_boost": float(os.environ.get("ELEVENLABS_SIMILARITY", 0.8)),
            "style": float(os.environ.get("ELEVENLABS_STYLE", 0.0)),
            "use_speaker_boost": True,
        }

    def speak(self, voice: str, text: str, dest: Path) -> int:
        missing = [k for k, v in (("ELEVENLABS_API_KEY", self.key), ("MATT_VOICE_ID", self.voices["MATT"]),
                                  ("JACK_VOICE_ID", self.voices["JACK"])) if not v]
        if missing:
            raise Blocked(f"set {', '.join(missing)} in .env (see .env.example)")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voices[voice]}?output_format=mp3_44100_128"
        body = json.dumps({"text": text, "model_id": self.model, "voice_settings": self.settings}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"xi-api-key": self.key, "Content-Type": "application/json"})
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".part")
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
                while chunk := r.read(1 << 16):
                    f.write(chunk)
        except urllib.error.HTTPError as e:
            raise Blocked(f"ElevenLabs refused a line ({e.code}): {e.read()[:200]!r}") from e
        os.replace(part, dest)
        return len(text)


class FakeVoice:
    ext = ".wav"

    def speak(self, voice: str, text: str, dest: Path) -> int:
        words = max(1, len(text.split()))
        media.tone(max(0.8, words / 2.6), dest, freq=196 if voice == "MATT" else 262)
        return len(text)


def generate_voiceover(st: EpisodeState, script: Path, out_dir: Path, backend: VoiceBackend, log: Log,
                       char_cap: int, control_check, redo: set[str] = frozenset()) -> dict[str, list[Path]]:
    """Voice every approved line once. Returns {part: [line files in order]}."""
    lines = parse_script(script)
    vs = st.data.setdefault("voice", {})
    used = sum(a.get("chars", 0) for v in vs.values() for a in v.get("attempts", []))
    parts: dict[str, list[Path]] = {}
    for ln in lines:
        control_check()
        entry = vs.setdefault(ln.key, {"status": "pending", "attempts": []})
        dest = out_dir / ln.part / f"{ln.row:02d}_{ln.speaker.lower()}{backend.ext}"
        fresh = entry["status"] == "done" and entry.get("text_hash") == ln.text_hash \
            and ln.key not in redo and media.done(dest)
        if not fresh:
            if len(entry["attempts"]) >= MAX_VOICE_ATTEMPTS and ln.key in redo:
                raise Blocked(f"{ln.key}: still wrong after {MAX_VOICE_ATTEMPTS} takes; record it live or reword it")
            if used + len(ln.text) > char_cap:
                raise NeedsCredits(f"voice lines would pass the {char_cap}-character cap "
                                   f"(used {used}). Raise JTA_VOICE_CHAR_CAP in .env to continue.")
            if entry["attempts"] and entry["attempts"][-1]["status"] == "submitting":
                entry["attempts"][-1]["status"] = "lost"  # died mid-call; that take is gone
            entry["attempts"].append({"n": len(entry["attempts"]) + 1, "status": "submitting",
                                      "at": now(), "chars": len(ln.text), "speaker": ln.speaker})
            entry["status"] = "submitting"
            st.save()                                   # intent saved before the paid call
            if dest.exists():
                dest.unlink()
            backend.speak(ln.speaker, ln.text, dest)
            used += len(ln.text)
            entry["attempts"][-1]["status"] = "done"
            entry.update(status="done", text_hash=ln.text_hash, file=str(dest), text=ln.text, speaker=ln.speaker)
            st.save()
            log("voice", f"{ln.key} {ln.speaker}: {ln.text[:60]}")
        parts.setdefault(ln.part, []).append(dest)
    return parts
