"""Phase 5 executor: runs generation_plan.json against Higgsfield, crash-safe.

The order of operations for every submit is what makes restarts safe:

  1. check the cap               ledger.check(cost)          (stop and ask if over)
  2. save intent                 attempt -> "submitting" in state.json
  3. reserve credits             ledger: reserve
  4. call Higgsfield             backend.submit()
  5. save the job id             attempt -> "submitted" + job_id in state.json
  6. record the spend            ledger: submitted
  7. only now poll               backend.wait()

If the process dies:
  - before 4: reconcile finds no job in Higgsfield history -> released, retried
  - between 4 and 5: the job exists but we never saw its id. Reconcile finds it
    in history by its exact prompt and adopts it. It is never submitted again.
  - after 5: the job id is on disk, so restart just polls and collects it.
Completed jobs are downloaded and QC'd once; results are saved before the
job is marked done, so a restart never redoes finished work.
"""
from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path
from typing import Callable, Optional

from . import state as S
from .config import Paths, Settings
from .higgsfield import Backend, NetworkDown, NotSent, OutcomeUnknown, Rejected
from .ledger import CapReached, Ledger
from .runtime import Blocked, Control, Log, NeedsCredits, Offline, Paused
from .state import EpisodeState, now

PLACEHOLDER = re.compile(r"\{\{job:([^}]+)\}\}")
# qc(key, step, file, job_id) -> (keep, reason)
QcFn = Callable[[str, dict, Path, str], tuple[bool, str]]


def load_plan(path: Path) -> dict:
    return json.loads(path.read_text())


class Generator:
    def __init__(self, paths: Paths, st: EpisodeState, ledger: Ledger, backend: Backend,
                 qc: QcFn, control: Control, log: Log, settings: Settings):
        self.paths, self.st, self.ledger, self.hf = paths, st, ledger, backend
        self.qc, self.control, self.log, self.cfg = qc, control, log, settings
        plan = load_plan(paths.plan)
        self.steps = {s["key"]: s for s in plan["steps"]}
        self.order = [s["key"] for s in plan["steps"]]
        self.new_jobs_this_run = 0
        self._offline_since: Optional[float] = None
        self._backoff = 2.0

    # ------------------------------------------------------------------ main loop
    def run(self) -> None:
        self.st.ensure_jobs(list(self.steps.values()))
        self._sync_ledger()
        self._record_balance()
        while True:
            self.control.check()
            try:
                self._reconcile_unknown()
                self._submit_ready()
                self._poll()
                self._online()
            except (NetworkDown, NotSent) as e:
                self._offline(e)
                continue
            if self._all_finished():
                self._record_balance()
                return
            if self._canary_done():
                raise Paused(f"canary limit reached: {self.new_jobs_this_run} new job(s) submitted "
                             f"and collected. Check them, then `jta run` to continue.")
            time.sleep(self.cfg.poll_seconds)

    def _all_finished(self) -> bool:
        return all(j["status"] in (S.DONE, S.FALLBACK) for j in self.st.data["jobs"].values())

    def _canary_done(self) -> bool:
        if self.cfg.max_new_jobs is None or self.new_jobs_this_run < self.cfg.max_new_jobs:
            return False
        return not self.st.jobs_with(*S.ACTIVE)

    # ------------------------------------------------------------------ submit
    def _ready(self, key: str) -> bool:
        job = self.st.job(key)
        if job["status"] != S.PENDING:
            return False
        for dep in job["depends_on"]:
            d = self.st.job(dep)["status"]
            if d == S.FALLBACK:
                self._finish(key, S.FALLBACK, reason=f"its start frame {dep} fell back")
                return False
            if d != S.DONE:
                return False
        return True

    def _submit_ready(self) -> None:
        for key in self.order:
            if len(self.st.jobs_with(S.SUBMITTING, S.SUBMITTED)) >= self.cfg.max_in_flight:
                return
            if self.cfg.max_new_jobs is not None and self.new_jobs_this_run >= self.cfg.max_new_jobs:
                return
            self.control.check()
            if self._ready(key):
                self._submit(key)

    def _resolved_params(self, key: str) -> dict:
        params = copy.deepcopy(self.steps[key]["params"])

        def sub(v):
            if isinstance(v, str):
                m = PLACEHOLDER.fullmatch(v)
                if m:
                    jid = self.st.job(m.group(1)).get("done_job_id")
                    if not jid:
                        raise RuntimeError(f"{key}: {m.group(1)} has no finished job yet")
                    return jid
            if isinstance(v, list):
                return [sub(x) for x in v]
            if isinstance(v, dict):
                return {k: sub(x) for k, x in v.items()}
            return v
        return sub(params)

    def _attempts_used(self, key: str) -> int:
        return sum(1 for a in self.st.job(key)["attempts"] if a["status"] != "void")

    def _submit(self, key: str) -> None:
        step, job = self.steps[key], self.st.job(key)
        if self._attempts_used(key) >= S.MAX_ATTEMPTS:
            self._finish(key, S.FALLBACK, reason=f"{S.MAX_ATTEMPTS} attempts used")
            return
        params = self._resolved_params(key)

        # Reuse an untracked job with this exact prompt before paying for a new one.
        orphan = self._take_orphan(params.get("prompt", ""))
        n = len(job["attempts"]) + 1
        if orphan:
            job["attempts"].append({"n": n, "status": S.SUBMITTED, "job_id": orphan,
                                    "started_at": now(), "cost": 0, "prompt": params.get("prompt", ""),
                                    "note": "adopted an untracked job (already paid for)"})
            job["status"] = S.SUBMITTED
            self.st.save()
            self.log("adopt", f"{key}: reused untracked job {orphan[:8]} instead of generating again")
            return

        cost = self.hf.get_cost(step["tool"], params)                # may raise NetworkDown
        try:
            self.ledger.check(cost, f"{key} (attempt {n})")
        except CapReached as e:
            raise NeedsCredits(f"{e} Approve more with: jta approve-credits {self.paths.episode} "
                               f"--extra {max(50, int(e.needed + 0.999))}") from e

        attempt = {"n": n, "status": S.SUBMITTING, "job_id": None, "started_at": now(),
                   "cost": cost, "prompt": params.get("prompt", "")}
        job["attempts"].append(attempt)
        job["status"] = S.SUBMITTING
        self.st.save()                                                # 2. intent on disk
        self.ledger.reserve(key, n, cost)                             # 3. credits reserved

        declined: Optional[str] = None
        for _ in range(2):                                            # one retry for a preset suggestion
            send = dict(params, declined_preset_id=declined) if declined else params
            try:
                res = self.hf.submit(step["tool"], send)              # 4. the paid call
            except NotSent:
                attempt["status"] = "void"
                job["status"] = S.PENDING
                self.st.save()
                self.ledger.void(key, n, "request never sent (no connection)")
                raise
            except Rejected as e:
                attempt["status"] = "void"
                attempt["error"] = str(e)[:300]
                self.ledger.void(key, n, f"rejected: {str(e)[:120]}")
                if "credit" in str(e).lower() or "balance" in str(e).lower():
                    job["status"] = S.PENDING
                    self.st.save()
                    raise Blocked(f"Higgsfield refused {key}: {str(e)[:200]}") from e
                attempt["status"] = "rejected"
                job["status"] = S.PENDING
                self.st.save()
                self.log("rejected", f"{key} attempt {n}: {str(e)[:120]}")
                return
            except OutcomeUnknown as e:
                attempt["status"] = S.UNKNOWN
                job["status"] = S.UNKNOWN
                self.st.save()
                self.log("unknown", f"{key}: submit outcome unknown ({str(e)[:80]}); will check history")
                return
            if res.job_ids:
                break
            if res.preset_id and not declined:
                declined = res.preset_id
                self.log("preset", f"{key}: Higgsfield suggested preset {res.preset_id}; resubmitting declined")
                continue
            if res.needs_human:
                attempt["status"] = "void"
                job["status"] = S.PENDING
                self.st.save()
                self.ledger.void(key, n, res.needs_human)
                raise Blocked(f"{key}: {res.needs_human}. Raw reply: {str(res.raw)[:300]}")
            attempt["status"] = S.UNKNOWN                              # couldn't read a job id
            job["status"] = S.UNKNOWN
            attempt["raw"] = str(res.raw)[:500]
            self.st.save()
            self.log("unknown", f"{key}: no job id in the reply; will check history")
            return

        jid = res.job_ids[0]
        attempt.update(status=S.SUBMITTED, job_id=jid, submitted_at=now())
        job["status"] = S.SUBMITTED
        self.st.save()                                                # 5. job id on disk
        self.ledger.submitted(key, n, jid, cost)                      # 6. spend recorded
        self.new_jobs_this_run += 1
        for extra in res.job_ids[1:]:                                 # never expected; never lost
            self._add_orphan(extra, "extra job id in one submit reply", params.get("prompt", ""), cost)
        self.log("submitted", f"{key} attempt {n} -> job {jid[:8]} ({cost:g} cr)")

    # ------------------------------------------------------------------ poll / collect
    def _poll(self) -> None:
        live = {}
        for key in self.st.jobs_with(S.SUBMITTED):
            a = self.st.current_attempt(key)
            live[a["job_id"]] = key
        if not live:
            return
        statuses = self.hf.wait(list(live), timeout=10 if not self.paths.dry_run else 0)
        for jid, stt in statuses.items():
            key = live.get(jid)
            if key is None or stt.state == "active":
                continue
            if stt.state == "completed":
                self._collect(key, jid, stt.result_url)
            else:
                a = self.st.current_attempt(key)
                a["status"] = "failed"
                a["error"] = stt.raw_status
                self.st.job(key)["status"] = S.PENDING
                self.st.save()
                self.log("failed", f"{key}: job {jid[:8]} failed on Higgsfield ({stt.raw_status})")

    def _collect(self, key: str, jid: str, url: Optional[str]) -> None:
        job, a = self.st.job(key), self.st.current_attempt(key)
        a["status"] = "completed"
        a["result_url"] = url
        self.st.save()
        ext = ".png" if self.steps[key]["tool"] == "generate_image" else ".mp4"
        dest = self.paths.media / "raw" / f"{key}_a{a['n']}{ext}"
        if not (dest.exists() and dest.stat().st_size > 0):
            self.hf.download(url, dest)                               # may raise NetworkDown; retried
        if "qc" not in a:
            keep, reason = self.qc(key, self.steps[key], dest, jid)
            a["qc"] = {"keep": keep, "reason": reason, "at": now()}
            self.st.save()
        if a["qc"]["keep"]:
            job["result_url"] = url
            job["file"] = str(dest.relative_to(self.paths.base))
            job["done_job_id"] = jid
            self._finish(key, S.DONE)
            self.log("done", f"{key}: kept ({a['qc']['reason']})")
        else:
            job["status"] = S.PENDING
            self.st.save()
            self.log("qc-reject", f"{key} attempt {a['n']}: {a['qc']['reason']}")

    def _finish(self, key: str, status: str, reason: str = "") -> None:
        job = self.st.job(key)
        job["status"] = status
        if reason:
            job["reason"] = reason
        self.st.save()
        if status == S.FALLBACK:
            self.log("fallback", f"{key}: moving to animation ({reason})")

    # ------------------------------------------------------------------ reconcile
    def _reconcile_unknown(self) -> None:
        """Resolve submits whose outcome we never saw, using Higgsfield history.

        Never resubmits on a guess: a job counts as "not created" only after
        unknown_settle seconds with no matching job in history.
        """
        todo = [k for k in self.st.jobs_with(S.SUBMITTING, S.UNKNOWN)]
        if not todo:
            return
        history = self.hf.history()
        known = self.st.known_job_ids() | set(self.st.data.get("orphans", {}))
        claimed: set[str] = set()
        for key in todo:
            a = self.st.current_attempt(key)
            matches = sorted(
                (h for h in history
                 if h.prompt == a["prompt"] and h.job_id not in known and h.job_id not in claimed
                 and h.created_at >= a["started_at"] - 300),
                key=lambda h: h.created_at)
            if matches:
                h = matches[0]
                claimed.add(h.job_id)
                a.update(status=S.SUBMITTED, job_id=h.job_id, submitted_at=now(),
                         note="found in Higgsfield history after a crash or timeout")
                self.st.job(key)["status"] = S.SUBMITTED
                self.st.save()
                self.ledger.submitted(key, a["n"], h.job_id, a["cost"])
                self.log("reconciled", f"{key}: found job {h.job_id[:8]} in history; adopted, not resubmitted")
            elif now() - a["started_at"] >= self.cfg.unknown_settle:
                a["status"] = "void"
                a["note"] = "no matching job in Higgsfield history"
                self.st.job(key)["status"] = S.PENDING
                self.st.save()
                self.ledger.void(key, a["n"], "not in Higgsfield history after settle time")
                self.log("reconciled", f"{key}: no job was created; will submit again")
        # Anything else in history with one of our prompts, created during this
        # episode and not tracked, was paid for: record it so it can be reused.
        ours = {s["params"].get("prompt") for s in self.steps.values()}
        start = self.st.data["created_at"] - 60
        for h in history:
            if h.prompt in ours and h.job_id not in known and h.job_id not in claimed \
                    and h.created_at >= start and h.status not in ("failed", "error"):
                cost = next(s["credits"] for s in self.steps.values() if s["params"].get("prompt") == h.prompt)
                self._add_orphan(h.job_id, "untracked job with one of this episode's prompts", h.prompt, cost)

    def _add_orphan(self, job_id: str, note: str, prompt: str, credits: float) -> None:
        """A job we paid for but weren't tracking. Counted as spent; reused if a step needs that prompt."""
        orphans = self.st.data.setdefault("orphans", {})
        if job_id in orphans:
            return
        orphans[job_id] = {"prompt": prompt, "note": note, "at": now(), "used_by": None, "credits": credits}
        self.st.save()
        self.ledger.orphan(job_id, credits, note)
        self.log("orphan", f"untracked job {job_id[:8]} recorded ({note})")

    def _take_orphan(self, prompt: str) -> Optional[str]:
        for jid, o in self.st.data.get("orphans", {}).items():
            if o["used_by"] is None and o["prompt"] and o["prompt"] == prompt:
                o["used_by"] = "adopted"
                return jid
        return None

    # ------------------------------------------------------------------ bookkeeping
    def _sync_ledger(self) -> None:
        """If we died between saving a job id and writing the ledger line, add the line now."""
        submitted = {(e["key"], e["attempt"]) for e in self.ledger._entries() if e["kind"] == "submitted"}
        for key, job in self.st.data["jobs"].items():
            for a in job["attempts"]:
                if a.get("job_id") and a.get("cost") and (key, a["n"]) not in submitted:
                    self.ledger.submitted(key, a["n"], a["job_id"], a["cost"])

    def _record_balance(self) -> None:
        try:
            b = self.hf.balance()
        except (NetworkDown, NotSent):
            return
        if b is not None:
            self.ledger.balance(b)

    def _online(self) -> None:
        if self._offline_since is not None:
            self.log("online", f"connection back after {now() - self._offline_since:.0f}s; continuing")
        self._offline_since = None
        self._backoff = 2.0

    def _offline(self, e: Exception) -> None:
        if self._offline_since is None:
            self._offline_since = now()
            self.log("offline", f"lost connection ({str(e)[:80]}); retrying with backoff")
        gone = now() - self._offline_since
        if gone > self.cfg.offline_patience:
            raise Offline(f"no connection for {gone:.0f}s. Everything is saved; "
                          f"run `jta resume {self.paths.episode}` when you're back online.")
        delay = min(self._backoff, 60.0, max(0.2, self.cfg.offline_patience - gone))
        deadline = time.time() + delay
        while time.time() < deadline:
            self.control.check()
            time.sleep(min(0.2, delay))
        self._backoff = min(self._backoff * 2, 60.0)
