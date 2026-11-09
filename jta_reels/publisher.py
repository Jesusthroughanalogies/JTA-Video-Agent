"""Publisher: posts the next ready reel as an Instagram trial reel when a slot is due.

Run it every 10 minutes from any scheduler. Each run does at most one thing:
  1. settle a reel left half-posted by an earlier run, or
  2. post the next reel into a due slot.

Why it can't double-post:
- One run at a time (Postgres advisory lock), one live reel per slot (unique index),
  and a daily cap counted in US Eastern days.
- The container id is saved before publishing. A run that dies or loses the network
  during media_publish leaves the reel in "publishing"; the next run reads the
  container: PUBLISHED means it went out (find the media id, never publish again),
  FINISHED means it didn't (publish now).
- media_publish is never retried blindly.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Callable

from . import schedule
from .db import DB
from .instagram import GraphError, Instagram
from .jobs import Result
from .rules import caption_problems

UTC = dt.timezone.utc
JOB = "publisher"
MAX_CANDIDATES = 4            # reels tried in one run when earlier ones fail the caption check


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _ig_time(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None


class Publisher:
    def __init__(self, db: DB, ig: Instagram, storage, alert: Callable[[str], None],
                 now: Callable[[], dt.datetime] = lambda: dt.datetime.now(UTC),
                 wait_timeout: float = 900, poll: float = 10):
        self.db, self.ig, self.storage, self.alert, self.now = db, ig, storage, alert, now
        self.wait_timeout, self.poll = wait_timeout, poll

    # ---- entry point ------------------------------------------------------------
    def run(self, force_slot: int | None = None) -> Result:
        with self.db.lock("jta-reels:publisher") as got:
            if not got:
                return Result("skipped:locked")
            for reel in self.db.in_flight():
                return self.settle(reel)
            return self.post_next(force_slot)

    # ---- 1. a reel an earlier run left in "publishing" -----------------------------
    def settle(self, reel: dict) -> Result:
        st = self.ig.container_status(reel["ig_container_id"])
        if st.code == "PUBLISHED":
            return self._adopt(reel)
        if st.code in ("ERROR", "EXPIRED"):
            return self._failed(reel, f"container {st.code}: {st.detail}")
        return self._finish(reel)          # IN_PROGRESS or FINISHED: wait, then publish

    # ---- 2. the next due slot ---------------------------------------------------------
    def post_next(self, force_slot: int | None) -> Result:
        tz = self.db.setting("timezone", "America/New_York")
        times = self.db.setting("slot_times", ["08:00", "12:00", "16:00", "20:00"])
        now = self.now()
        if force_slot:
            day = schedule.local_day(now, tz)
            slots = [s for s in schedule.slots_on(day, times, tz) if s.number == force_slot]
        else:
            slots = schedule.due_slots(now, times, tz, float(self.db.setting("slot_catchup_hours", 3)))
        slots = [s for s in slots if not self.db.slot_used(s.day, s.number)]
        if not slots:
            return Result("skipped:nothing_due")
        slot = slots[0]
        key = f"{slot.day}#{slot.number}"

        start, end = schedule.day_bounds_utc(slot.day, tz)
        cap = int(self.db.setting("daily_cap", 4))
        if self.db.live_between(start, end) >= cap:
            return Result("skipped:daily_cap", detail={"slot": key, "cap": cap})

        for _ in range(MAX_CANDIDATES):
            reel = self.db.next_ready(slot.day, slot.number)
            if reel is None:
                if not self.db.one("select 1 as x from job_runs where job = %s and outcome = 'skipped:no_reel' "
                                   "and detail->>'slot' = %s", (JOB, key)):
                    self.alert(f"slot {slot.number} ({slot.at:%a %H:%M} ET) is due but no reel is ready")
                return Result("skipped:no_reel", detail={"slot": key})
            problems = caption_problems(reel["caption"])
            if problems:
                self.db.add_check(reel["id"], "caption", False, "; ".join(problems))
                self.db.update_reel(reel["id"], status="failed_check", status_note="; ".join(problems))
                self.alert(f"reel {reel['id']} blocked by the caption check: {'; '.join(problems)}")
                continue
            return self._post(reel, slot)
        return Result("skipped:no_valid_reel", detail={"slot": key})

    def _post(self, reel: dict, slot: schedule.Slot) -> Result:
        url = self.storage.get_url(reel["video_key"])
        strategy = self.db.setting("graduation_strategy", "MANUAL")
        try:
            cid = self.ig.create_trial_reel(url, reel["caption"], strategy=strategy)
        except GraphError as e:
            if e.transient:     # nothing was created that matters; the reel stays ready for the next run
                raise
            return self._failed(reel, f"Instagram refused the container: {e}")
        # Saved before publishing: from here on, a crash is settled from the container's status.
        self.db.update_reel(reel["id"], status="publishing", ig_container_id=cid,
                            batch_date=slot.day, slot=slot.number, status_note=None)
        return self._finish(self.db.reel(reel["id"]))

    def _finish(self, reel: dict) -> Result:
        cid = reel["ig_container_id"]
        try:
            st = self.ig.wait_until_ready(cid, timeout=self.wait_timeout, poll=self.poll)
        except TimeoutError:
            return Result("waiting:container", detail={"reel": str(reel["id"]), "container": cid})
        except GraphError as e:
            if e.transient:
                raise
            return self._failed(reel, str(e))
        if st.code == "PUBLISHED":
            return self._adopt(reel)
        try:
            media_id = self.ig.publish(cid)
        except GraphError as e:
            if e.transient:
                self.db.update_reel(reel["id"], status_note="publish outcome unknown; next run reads the container")
                return Result("error", ok=False, error=f"publish outcome unknown, will check the container: {e}",
                              detail={"reel": str(reel["id"])})
            return self._failed(reel, f"media_publish refused: {e}")
        return self._posted(reel, media_id, self.now())

    # ---- outcomes ---------------------------------------------------------------------
    def _posted(self, reel: dict, media_id: str, posted_at: dt.datetime) -> Result:
        self.db.update_reel(reel["id"], status="posted", ig_media_id=media_id, posted_at=posted_at, status_note=None)
        detail = {"reel": str(reel["id"]), "media_id": media_id, "slot": f"{reel['batch_date']}#{reel['slot']}"}
        try:
            m = self.ig.media(media_id)
            self.db.update_reel(reel["id"], permalink=m.get("permalink"))
            detail["permalink"] = m.get("permalink")
            if m.get("media_product_type") not in (None, "REELS"):
                self.alert(f"reel {reel['id']} posted as {m.get('media_product_type')}, not REELS")
        except GraphError:
            pass                      # the permalink is cosmetic; insights fills it in later
        return Result("posted", detail=detail)

    def _adopt(self, reel: dict) -> Result:
        """The container says PUBLISHED but we never saved the media id. Find it; never publish again."""
        since = reel["updated_at"] - dt.timedelta(hours=1)
        for m in self.ig.recent_media(limit=25):
            t = _ig_time(m.get("timestamp", ""))
            if _norm(m.get("caption")) == _norm(reel["caption"]) and (t is None or t >= since):
                return self._posted(reel, str(m["id"]), t or self.now())
        return self._failed(reel, "container is PUBLISHED but the post wasn't found in recent media. "
                                  "Check the app; the reel will not be posted again")

    def _failed(self, reel: dict, why: str) -> Result:
        self.db.update_reel(reel["id"], status="failed_publish", status_note=why[:1000])
        return Result("failed_publish", ok=False, error=why, detail={"reel": str(reel["id"])})
