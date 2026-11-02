"""Shot model, prompt builder and validator for JTA AI shots."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import rules


@dataclass
class Shot:
    id: str                      # e.g. "P2-01"
    tag: str                     # AI | ANIM | TEXT | CLIP | PHOTO | STOCK
    words: str = ""              # the voiceover line (for the editor and checks)
    # AI fields
    camera: str = ""             # "Slow push-in."
    scene: str = ""              # subject, action and setting, concrete and physical
    light: str = ""              # "Dawn, low golden sun, rim light."
    mood: str = ""               # "Awe and longing."
    jesus: bool = False          # uses the JTA-Jesus character (two-step generation)
    people: bool = False         # other people in frame (adds the dress rule)
    nature: bool = False         # pure nature or space, no people or buildings
    hero: bool = False           # 2 variants instead of 1
    reuse: Optional[str] = None  # job id of an approved clip; costs nothing
    start_frame: Optional[str] = None  # job id of an approved Jesus start frame
    # non-AI fields
    spec: str = ""               # ANIM / TEXT / CLIP / PHOTO description
    background: Optional[str] = None  # TEXT card background: id of an AI shot to reuse
    notes: str = ""

    @property
    def variants(self) -> int:
        return 2 if self.hero else 1


def build_video_prompt(s: Shot) -> str:
    """Camera, subject, setting, light, lens, mood, then the fixed ending."""
    scene = s.scene.replace("{JESUS}", rules.JESUS_TOKEN)
    parts = [s.camera, scene, s.light, rules.LENS, s.mood]
    if s.jesus:
        parts.append(rules.JESUS_RULES)
    if s.people:
        parts.append(rules.OTHER_PEOPLE_DRESS)
    parts.append(rules.NATURE_ENDING if s.nature else rules.ANCIENT_ENDING)
    return " ".join(p.strip() for p in parts if p and p.strip())


def build_frame_prompt(s: Shot) -> str:
    """Start-frame prompt for Jesus shots (a still, so no camera move)."""
    scene = s.scene.replace("{JESUS}", rules.JESUS_TOKEN)
    parts = ["Cinematic film still.", scene, s.light, rules.LENS, rules.JESUS_RULES]
    if s.people:
        parts.append(rules.OTHER_PEOPLE_DRESS)
    parts.append(rules.ANCIENT_ENDING)
    return " ".join(p.strip() for p in parts if p and p.strip())


def _description_only(s: Shot) -> str:
    """The part of the prompt we wrote ourselves (the negative ending is exempt)."""
    return " ".join([s.camera, s.scene, s.light, s.mood]).lower()


def validate(s: Shot) -> list[str]:
    errors: list[str] = []
    if s.tag not in {"AI", "ANIM", "TEXT", "CLIP", "PHOTO", "STOCK"}:
        errors.append(f"{s.id}: unknown tag {s.tag}")
    if s.tag != "AI":
        if not s.spec:
            errors.append(f"{s.id}: {s.tag} shot needs a spec")
        return errors
    if s.reuse:
        return errors
    if not (s.camera and s.scene and s.light):
        errors.append(f"{s.id}: AI shot needs camera, scene and light")
    text = f" {_description_only(s)} "
    for w in rules.BANNED_WORDS:
        pattern = r"\b" + re.escape(w.strip()) + r"\b"
        if re.search(pattern, text):
            errors.append(f"{s.id}: modern word in scene: '{w.strip()}'")
    if s.jesus and "{JESUS}" not in s.scene:
        errors.append(f"{s.id}: Jesus shot must place {{JESUS}} in the scene")
    if not s.jesus and "{JESUS}" in s.scene:
        errors.append(f"{s.id}: {{JESUS}} used but jesus=False")
    if s.jesus and re.search(r"\b(face|faces|turns? (around|to camera))\b", text) and "never" not in text:
        errors.append(f"{s.id}: Jesus shot mentions his face")
    if s.nature and s.people:
        errors.append(f"{s.id}: nature shots can't have people")
    return errors
