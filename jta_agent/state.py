"""Episode state: where the pipeline is, saved after every step.

episodes/<id>/state.json holds:
  phase / status       which phase is running and whether we are running,
                       paused or waiting for a human
  checkpoints          A to D approvals
  phases               per-phase step progress (a step is recorded done only
                       after its output is on disk)
  jobs                 one entry per Higgsfield generation step from
                       generation_plan.json, with every attempt and its job id
  summary              shots done / in flight / pending, for a quick read

The file is rewritten atomically after every change (store.write_json).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from . import store

PHASES = ["topic", "script", "ingest", "shotlist", "generate", "assemble", "package", "learn"]
CHECKPOINT_AFTER = {"topic": "A", "script": "B", "shotlist": "C", "assemble": "D"}

# Job (generation step) statuses
PENDING = "pending"          # not started
SUBMITTING = "submitting"    # credits reserved, submit call in progress
SUBMITTED = "submitted"      # job id saved, waiting for Higgsfield
UNKNOWN = "unknown"          # submit outcome unknown (crash or timeout mid-call)
DONE = "done"                # completed, downloaded and passed QC
FALLBACK = "fallback"        # failed or rejected 3 times: move to animation
ACTIVE = (SUBMITTING, SUBMITTED, UNKNOWN)

MAX_ATTEMPTS = 3


def now() -> float:
    return round(time.time(), 3)


class EpisodeState:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data

    # ---- load / save ---------------------------------------------------
    @classmethod
    def create(cls, path: Path, episode_id: str, mode: str, start_at: str = "topic") -> "EpisodeState":
        if path.exists():
            raise FileExistsError(f"{path} already exists; use `jta run` to continue it")
        phases = {}
        for p in PHASES:
            done = PHASES.index(p) < PHASES.index(start_at)
            phases[p] = {"status": "done" if done else "pending", "steps": {},
                         "note": "done outside the agent" if done else ""}
        checkpoints = {}
        for p, cp in CHECKPOINT_AFTER.items():
            # Spend approval (C) is never implied by where you start: it must be given explicitly.
            done = PHASES.index(p) < PHASES.index(start_at) and cp != "C"
            checkpoints[cp] = {"approved": done, "at": now() if done else None,
                               "by": "pre-existing" if done else None}
        data = {
            "episode_id": episode_id,
            "mode": mode,
            "phase": start_at,
            "status": "running",
            "status_reason": "",
            "checkpoints": checkpoints,
            "phases": phases,
            "jobs": {},
            "created_at": now(),
            "updated_at": now(),
        }
        st = cls(path, data)
        st.save()
        return st

    @classmethod
    def load(cls, path: Path) -> "EpisodeState":
        data = store.read_json(path)
        if data is None:
            raise FileNotFoundError(f"no state at {path}; start the episode with `jta new`")
        return cls(path, data)

    def save(self) -> None:
        self.data["updated_at"] = now()
        self.data["summary"] = self.summary()
        store.write_json(self.path, self.data)

    # ---- phase / status --------------------------------------------------
    @property
    def phase(self) -> str:
        return self.data["phase"]

    @property
    def status(self) -> str:
        return self.data["status"]

    def set_status(self, status: str, reason: str = "") -> None:
        self.data["status"] = status
        self.data["status_reason"] = reason
        self.save()

    def phase_data(self, phase: str) -> dict:
        return self.data["phases"][phase]

    def step_done(self, phase: str, step: str) -> bool:
        return self.phase_data(phase)["steps"].get(step, {}).get("done", False)

    def mark_step(self, phase: str, step: str, **info: Any) -> None:
        self.phase_data(phase)["steps"][step] = {"done": True, "at": now(), **info}
        self.save()

    def finish_phase(self, phase: str) -> None:
        self.phase_data(phase)["status"] = "done"
        i = PHASES.index(phase)
        self.data["phase"] = PHASES[i + 1] if i + 1 < len(PHASES) else "finished"
        self.save()

    def checkpoint(self, cp: str) -> dict:
        return self.data["checkpoints"][cp]

    def approve(self, cp: str, by: str, note: str = "") -> None:
        self.data["checkpoints"][cp] = {"approved": True, "at": now(), "by": by, "note": note}
        if self.status == "awaiting_approval":
            self.data["status"] = "running"
            self.data["status_reason"] = ""
        self.save()

    # ---- generation jobs ---------------------------------------------------
    def ensure_jobs(self, steps: list[dict]) -> None:
        """Register plan steps once. Existing entries (and their job ids) are kept."""
        changed = False
        for s in steps:
            if s["key"] not in self.data["jobs"]:
                self.data["jobs"][s["key"]] = {
                    "status": PENDING,
                    "tool": s["tool"],
                    "depends_on": s.get("depends_on", []),
                    "attempts": [],
                    "result_url": None,
                    "file": None,
                }
                changed = True
        if changed:
            self.save()

    def job(self, key: str) -> dict:
        return self.data["jobs"][key]

    def jobs_with(self, *statuses: str) -> list[str]:
        return [k for k, j in self.data["jobs"].items() if j["status"] in statuses]

    def known_job_ids(self) -> set[str]:
        return {a["job_id"] for j in self.data["jobs"].values() for a in j["attempts"] if a.get("job_id")}

    def current_attempt(self, key: str) -> Optional[dict]:
        a = self.job(key)["attempts"]
        return a[-1] if a else None

    # ---- summary -------------------------------------------------------------
    def summary(self) -> dict:
        jobs = self.data["jobs"]

        def shot(k: str) -> str:
            return k.rsplit("-v", 1)[0]

        done = sorted({shot(k) for k, j in jobs.items() if j["status"] == DONE
                       and not k.endswith("-frame")})
        flight = sorted(k for k, j in jobs.items() if j["status"] in ACTIVE)
        pending = sorted(k for k, j in jobs.items() if j["status"] == PENDING)
        fallback = sorted(k for k, j in jobs.items() if j["status"] == FALLBACK)
        return {
            "phase": self.data["phase"],
            "status": self.data["status"],
            "jobs_total": len(jobs),
            "jobs_done": sum(1 for j in jobs.values() if j["status"] == DONE),
            "shots_done": done,
            "jobs_in_flight": flight,
            "jobs_pending": pending,
            "jobs_fallback": fallback,
        }
