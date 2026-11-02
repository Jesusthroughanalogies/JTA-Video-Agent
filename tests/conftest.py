import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ep_test"
sys.path.insert(0, str(ROOT))


@pytest.fixture
def episode():
    """A throwaway copy of the test fixture episode (shots, plan, script) under episodes/_test_xxxx.

    The fixture is a frozen copy of Ep 1 with nothing pre-generated, so these tests keep working
    after real episodes have their clips approved (which leaves nothing to generate)."""
    name = f"_test_{uuid.uuid4().hex[:8]}"
    d = ROOT / "episodes" / name
    d.mkdir(parents=True)
    for f in ("shots.py", "generation_plan.json", "script.md"):
        shutil.copy(FIXTURE / f, d / f)
    yield name
    shutil.rmtree(d, ignore_errors=True)


class Run:
    """Drive the real CLI in a subprocess, the way you would from a terminal."""

    def __init__(self, episode: str, **env):
        self.episode = episode
        self.base = ROOT / "episodes" / episode / "dryrun"
        self.env = {**os.environ, "JTA_FAKE_JOB_SECONDS": "2", "PYTHONUNBUFFERED": "1", **env}

    def cmd(self, *args: str) -> list[str]:
        return [sys.executable, "-m", "jta_agent", *args, self.episode, "--dry-run"]

    def start(self, *extra: str, **env) -> subprocess.Popen:
        return subprocess.Popen(self.cmd("run", "--start-at", "generate", "--until", "generate",
                                         "--max-in-flight", "6", "--quiet", *extra),
                                cwd=ROOT, env={**self.env, **env}, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)

    def run(self, *extra: str, timeout: float = 240, **env) -> subprocess.CompletedProcess:
        p = self.start(*extra, **env)
        out, _ = p.communicate(timeout=timeout)
        return subprocess.CompletedProcess(p.args, p.returncode, out, "")

    def other(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(self.cmd(*args), cwd=ROOT, env=self.env, capture_output=True, text=True)

    # ---- inspection -------------------------------------------------------
    def server_jobs(self) -> list[dict]:
        f = self.base / "fake_server.json"
        return json.loads(f.read_text())["jobs"] if f.exists() else []

    def state(self) -> dict:
        return json.loads((self.base / "state.json").read_text())

    def events(self) -> list[dict]:
        f = self.base / "events.jsonl"
        return [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []

    def wait_for(self, cond, timeout: float = 60, every: float = 0.1) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if cond():
                    return
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(every)
        raise TimeoutError("condition not met")


def kill9(p: subprocess.Popen) -> None:
    p.send_signal(signal.SIGKILL)
    p.wait(timeout=10)


@pytest.fixture
def runner(episode):
    return Run(episode)
