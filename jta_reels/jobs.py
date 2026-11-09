"""The wrapper every job runs inside: kill switch, run log, and "fails twice, stops"."""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Callable

from .db import DB

OK, SKIPPED, ERROR = 0, 2, 1      # exit codes


@dataclass
class Result:
    outcome: str                   # "posted", "skipped:paused", "nothing_due" ...
    ok: bool = True
    detail: dict = field(default_factory=dict)
    cost_usd: float | None = None
    error: str | None = None

    @property
    def exit_code(self) -> int:
        if not self.ok:
            return ERROR
        return SKIPPED if self.outcome.startswith("skipped") else OK


def run_job(db: DB, job: str, fn: Callable[[], Result], alert: Callable[[str], None]) -> Result:
    """Run one job. Paused or stopped jobs don't start. Two failures in a row stop the job
    (it alerts and won't run again until `jta-reels unstop <job>`), instead of retrying forever."""
    if db.is_paused():
        return Result("skipped:paused")
    if job in (db.setting("stopped_jobs", []) or []):
        return Result("skipped:stopped")
    run_id = db.start_run(job)
    try:
        res = fn()
    except Exception as e:
        res = Result("error", ok=False, error=f"{type(e).__name__}: {e}",
                     detail={"trace": traceback.format_exc()[-4000:]})
    db.finish_run(run_id, ok=res.ok, outcome=res.outcome, error=res.error, detail=res.detail, cost_usd=res.cost_usd)
    if res.ok:
        return res
    prev = db.last_runs(job, 2)
    if len(prev) == 2 and all(r["ok"] is False for r in prev):
        stopped = list(db.setting("stopped_jobs", []) or [])
        if job not in stopped:
            db.set_setting("stopped_jobs", stopped + [job])
        alert(f"{job} failed twice in a row and is stopped. Last error: {res.error}. "
              f"Fix it, then run: jta-reels unstop {job}")
    else:
        alert(f"{job} failed: {res.error}")
    return res
