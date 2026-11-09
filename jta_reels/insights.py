"""Insights pull: snapshots of every recent trial reel at 6 h, 24 h, 48 h and 7 days.

Runs every 6 hours. A snapshot is filed under the largest bucket the reel has passed and
not yet filled, with the reel's real age stored next to it. Metrics Meta won't give for
reels are remembered in settings.insights_unsupported and not asked for again.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

from .db import DB
from .instagram import REEL_METRICS, GraphError, Instagram
from .jobs import Result

UTC = dt.timezone.utc
JOB = "insights"

# Meta metric name -> metrics column. Watch times arrive in milliseconds.
COLUMNS = {"views": "views", "reach": "reach", "likes": "likes", "comments": "comments",
           "shares": "shares", "saved": "saves", "follows": "follows", "profile_visits": "profile_visits"}
MS_COLUMNS = {"ig_reels_avg_watch_time": "avg_watch_s", "ig_reels_video_view_total_time": "total_watch_s"}


def to_row(values: dict) -> dict:
    row = {col: values.get(m) for m, col in COLUMNS.items() if values.get(m) is not None}
    for m, col in MS_COLUMNS.items():
        if values.get(m) is not None:
            row[col] = round(float(values[m]) / 1000.0, 2)
    return row


class InsightsPull:
    def __init__(self, db: DB, ig: Instagram, alert: Callable[[str], None],
                 now: Callable[[], dt.datetime] = lambda: dt.datetime.now(UTC)):
        self.db, self.ig, self.alert, self.now = db, ig, alert, now

    def run(self) -> Result:
        now = self.now()
        buckets = sorted(int(b) for b in self.db.setting("insights_buckets", [6, 24, 48, 168]))
        unsupported = set(self.db.setting("insights_unsupported", []) or [])
        metrics = [m for m in REEL_METRICS if m not in unsupported]
        signal = self.db.setting("graduation_signal", "manual")
        taken, errors, newly_unsupported, graduated = 0, {}, set(), []

        for reel in self.db.reels_for_insights(now - dt.timedelta(hours=max(buckets) + 24)):
            age = (now - reel["posted_at"]).total_seconds() / 3600
            passed = [b for b in buckets if age >= b]
            if not passed or passed[-1] in self.db.buckets_taken(reel["id"]):
                continue                    # a missed earlier bucket stays empty, never back-filled late
            bucket = passed[-1]
            mid = reel["ig_media_id"]
            try:
                values, unsup = self.ig.insights(mid, metrics)
                shared_ok, shared = self.ig.media_field(mid, "is_shared_to_feed")
            except GraphError as e:
                if e.transient:
                    raise
                errors[str(reel["id"])] = str(e)      # e.g. the post was deleted; don't stop the others
                continue
            newly_unsupported |= set(unsup) - unsupported
            row = to_row(values)
            if shared_ok:
                row["is_shared_to_feed"] = shared
            raw = {"values": values, "unsupported": unsup, "is_shared_to_feed": shared if shared_ok else None}
            self.db.add_metrics(reel["id"], bucket, age, row, raw)
            taken += 1
            if signal == "is_shared_to_feed" and shared is True and reel["status"] == "posted":
                self.db.update_reel(reel["id"], status="graduated", graduated_at=now)
                graduated.append(str(reel["id"]))

        if newly_unsupported:
            self.db.set_setting("insights_unsupported", sorted(unsupported | newly_unsupported))
            if "follows" in newly_unsupported:
                self.alert("Instagram doesn't report follows per reel. The score falls back to profile visits "
                           "per 1,000 views (spec: Analyst, the score).")
        return Result("pulled", detail={"snapshots": taken, "errors": errors, "graduated": graduated,
                                        "newly_unsupported": sorted(newly_unsupported)})
