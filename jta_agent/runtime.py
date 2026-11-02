"""Run control: pause flag, signals, the event log, and the reasons a run stops."""
from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from . import store


class Stop(Exception):
    """A clean stop. The state is saved; `jta run` or `jta resume` continues."""
    status = "paused"


class Paused(Stop):
    status = "paused"


class NeedsApproval(Stop):
    status = "awaiting_approval"


class NeedsCredits(Stop):
    status = "awaiting_credit_approval"


class Offline(Stop):
    status = "paused"


class Blocked(Stop):
    status = "blocked"


class Control:
    """`jta pause` writes control.json; the running process checks it between
    steps. Ctrl-C and SIGTERM ask for the same clean pause."""

    def __init__(self, path: Path):
        self.path = path
        self._signalled = False

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            if self._signalled:  # second Ctrl-C: stop now (state is already saved)
                raise KeyboardInterrupt
            self._signalled = True
            print("\n[jta] pause requested; finishing the current save, then stopping...", file=sys.stderr)
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def request_pause(self, by: str) -> None:
        store.write_json(self.path, {"pause": True, "by": by, "at": time.time()})

    def clear(self) -> None:
        store.write_json(self.path, {"pause": False})

    def pause_requested(self) -> bool:
        if self._signalled:
            return True
        return bool((store.read_json(self.path, {}) or {}).get("pause"))

    def check(self) -> None:
        if self.pause_requested():
            raise Paused("paused on request")


class Log:
    def __init__(self, path: Path, quiet: bool = False):
        self.path = path
        self.quiet = quiet

    def __call__(self, event: str, msg: str = "", **fields) -> None:
        store.append_jsonl(self.path, {"t": round(time.time(), 3), "event": event, "msg": msg, **fields})
        if not self.quiet:
            stamp = time.strftime("%H:%M:%S")
            print(f"[{stamp}] {event:<12} {msg}", flush=True)
