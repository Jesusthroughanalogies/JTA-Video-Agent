"""Paths and settings for one episode run."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from jta_visuals import rules

REPO = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT_FILE = REPO / "claude" / "video-agent-system-prompt.md"
KNOWLEDGE_DIR = REPO / "knowledge"


def load_dotenv() -> None:
    """Load KEY=VALUE lines from .env into the environment if the file exists.

    Only the running agent reads .env. It is git-ignored and never committed.
    """
    p = REPO / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Paths:
    episode: str          # folder name under episodes/, e.g. "ep001"
    dry_run: bool

    @property
    def ep_dir(self) -> Path:
        return REPO / "episodes" / self.episode

    @property
    def base(self) -> Path:
        """Run files live here. Dry runs are kept apart so they never touch real state."""
        return self.ep_dir / "dryrun" if self.dry_run else self.ep_dir

    shots = property(lambda self: self.ep_dir / "shots.py")
    plan = property(lambda self: self.ep_dir / "generation_plan.json")
    state = property(lambda self: self.base / "state.json")
    ledger = property(lambda self: self.base / "ledger.jsonl")
    events = property(lambda self: self.base / "events.jsonl")
    control = property(lambda self: self.base / "control.json")
    lock = property(lambda self: self.base / ".lock")
    media = property(lambda self: self.base / "media")
    work = property(lambda self: self.base / "work")


@dataclass
class Settings:
    credit_cap: float = rules.EPISODE_CREDIT_CAP
    max_in_flight: int = 4            # Higgsfield PLUS allows 6 parallel videos
    poll_seconds: float = 5.0
    offline_patience: float = 30 * 60  # keep retrying this long, then pause
    unknown_settle: float = 90.0       # wait this long before deciding an unknown submit never happened
    max_new_jobs: int | None = None    # canary: stop after submitting this many
    auto_approve: bool = False         # dry runs approve checkpoints themselves
    use_llm: bool = True               # dry runs stub Claude unless --with-llm
    until: str | None = None           # stop cleanly after this phase

    @classmethod
    def for_mode(cls, dry_run: bool, **over) -> "Settings":
        s = cls()
        if dry_run:
            s.poll_seconds = 0.3
            s.unknown_settle = 1.0
            s.offline_patience = float(os.environ.get("JTA_OFFLINE_PATIENCE", 20))
            s.auto_approve = True
            s.use_llm = False
        for k, v in over.items():
            if v is not None:
                setattr(s, k, v)
        return s
