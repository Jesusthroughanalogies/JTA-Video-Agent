"""Dry-run backend: a fake Higgsfield that spends nothing.

It behaves like the real service in the ways that matter for crash safety:
- Jobs live in a server-side file (dryrun/fake_server.json), not in our
  process, so they keep "rendering" while the agent is dead and are still
  there after a restart, exactly like real Higgsfield jobs.
- Jobs take a few seconds to finish, can fail, and show up in history.
- Costs come from jta_visuals.rules (8.75 per clip, 2 per frame).

Fault injection (environment variables, used by the tests):
  JTA_FAKE_JOB_SECONDS=2           how long a job takes
  JTA_FAKE_FAIL_RATE=0.0           share of jobs that fail on the server
  JTA_FAKE_QC_REJECT_RATE=0.0      share of clips the fake QC rejects
  JTA_CRASH_AFTER_SUBMITS=N        kill the process right after the Nth job is
                                   created on the server but before the agent
                                   hears back (the worst moment to die)
  JTA_FAKE_OFFLINE_FILE=path       while this file exists, every call fails as
                                   if the wifi were down
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from jta_visuals import rules

from .higgsfield import HistoryItem, JobStatus, NetworkDown, NotSent, SubmitResult


def _rate(env: str, default: float = 0.0) -> float:
    try:
        return float(os.environ.get(env, default))
    except ValueError:
        return default


def _hash_unit(s: str) -> float:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


class FakeBackend:
    def __init__(self, root: Path, start_balance: float = 3000.0):
        self.root = root
        self.server = root / "fake_server.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.start_balance = start_balance
        self.job_seconds = _rate("JTA_FAKE_JOB_SECONDS", 2.0)

    # ---- server file (locked, so two processes never corrupt it) ----------
    @contextmanager
    def _db(self):
        lock = open(self.root / ".fake_server.lock", "a+")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            db = json.loads(self.server.read_text()) if self.server.exists() else \
                {"balance": self.start_balance, "jobs": []}
            yield db
            tmp = self.server.with_suffix(".tmp")
            tmp.write_text(json.dumps(db, indent=1))
            os.replace(tmp, self.server)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def _offline(self, mutating: bool) -> None:
        f = os.environ.get("JTA_FAKE_OFFLINE_FILE")
        if f and Path(f).exists():
            raise (NotSent if mutating else NetworkDown)("fake wifi is down")

    @staticmethod
    def _cost(tool: str) -> float:
        return rules.CREDITS_PER_FRAME if tool == "generate_image" else rules.CREDITS_PER_CLIP

    # ---- Backend interface --------------------------------------------------
    def get_cost(self, tool: str, params: dict) -> float:
        self._offline(False)
        return self._cost(tool)

    def submit(self, tool: str, params: dict) -> SubmitResult:
        self._offline(True)
        job_id = str(uuid.uuid4())
        crash_after = int(os.environ.get("JTA_CRASH_AFTER_SUBMITS", "0") or 0)
        with self._db() as db:
            fail = _hash_unit(job_id + "fail") < _rate("JTA_FAKE_FAIL_RATE")
            db["jobs"].append({
                "id": job_id, "tool": tool, "params": params, "created_at": time.time(),
                "ready_at": time.time() + self.job_seconds,
                "outcome": "failed" if fail else "completed",
            })
            db["balance"] = round(db["balance"] - self._cost(tool), 2)
            n = len(db["jobs"])
        if crash_after and n == crash_after:
            os._exit(137)  # the job exists on the server, but the agent never hears back
        return SubmitResult(job_ids=[job_id], raw={"job_id": job_id})

    def wait(self, job_ids: list[str], timeout: int = 15) -> dict[str, JobStatus]:
        self._offline(False)
        out = {}
        with self._db() as db:
            by_id = {j["id"]: j for j in db["jobs"]}
        for jid in job_ids:
            j = by_id.get(jid)
            if j is None:
                out[jid] = JobStatus(jid, "failed", "not_found")
            elif time.time() < j["ready_at"]:
                out[jid] = JobStatus(jid, "active", "in_progress")
            elif j["outcome"] == "failed":
                out[jid] = JobStatus(jid, "failed", "failed")
            else:
                ext = "png" if j["tool"] == "generate_image" else "mp4"
                out[jid] = JobStatus(jid, "completed", "completed", f"fake://{jid}.{ext}")
        return out

    def history(self, pages: int = 3, page_size: int = 50) -> list[HistoryItem]:
        self._offline(False)
        with self._db() as db:
            jobs = list(db["jobs"])
        items = []
        for j in sorted(jobs, key=lambda x: -x["created_at"])[: pages * page_size]:
            done = time.time() >= j["ready_at"]
            items.append(HistoryItem(j["id"], j["outcome"] if done else "in_progress",
                                     j["params"].get("prompt", ""), j["created_at"], j["params"].get("model", "")))
        return items

    def balance(self) -> Optional[float]:
        self._offline(False)
        with self._db() as db:
            return db["balance"]

    def download(self, url: str, dest: Path) -> None:
        self._offline(False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = self._template(url.endswith(".png"))
        shutil.copyfile(src, dest)

    # ---- helpers --------------------------------------------------------------
    def server_jobs(self) -> list[dict]:
        with self._db() as db:
            return list(db["jobs"])

    def _template(self, image: bool) -> Path:
        """One tiny placeholder clip/still, made once with ffmpeg."""
        p = self.root / ("template.png" if image else "template.mp4")
        if p.exists():
            return p
        if image:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                   "color=c=0x0E1A2B:s=640x360", "-frames:v", "1", str(p)]
        else:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                   "testsrc2=s=640x360:r=30:d=5", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                   "-preset", "ultrafast", str(p)]
        subprocess.run(cmd, check=True)
        return p


def fake_qc(job_id: str) -> tuple[bool, str]:
    if _hash_unit(job_id + "qc") < _rate("JTA_FAKE_QC_REJECT_RATE"):
        return False, "dry run: simulated reject (warped hands)"
    return True, "dry run: auto-pass"
