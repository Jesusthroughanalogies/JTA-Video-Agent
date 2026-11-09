"""jta-reels: the Trial Reel Agent's jobs and controls.

  jta-reels db migrate                 create or update the tables (Supabase)
  jta-reels status                     paused?, today's slots, queue, last runs
  jta-reels publish [--slot N]         post into the due slot (cron: every 10 minutes)
  jta-reels insights                   pull insights snapshots (cron: every 6 hours)
  jta-reels queue --file reel.mp4 --caption "..." [--slot N --date YYYY-MM-DD]
                                       add a ready reel by hand (until the Creator exists)
  jta-reels pause | resume             the kill switch: every job checks it first
  jta-reels unstop JOB                 restart a job that stopped after failing twice
  jta-reels get KEY | set KEY JSON     read or change a setting
  jta-reels probe ...                  Week 1 proof (see jta_reels/probe.py)

Exit codes: 0 done, 2 skipped (paused, nothing due, capped), 1 error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

from . import probe, schedule
from .alerts import Alerts, jsonable
from .config import Config, ConfigError
from .instagram import GRADUATION_STRATEGIES, Instagram
from .jobs import ERROR, OK, run_job

UTC = dt.timezone.utc


def _db(cfg: Config):
    from .db import DB     # psycopg is only needed for commands that touch the database
    cfg.require("database_url")
    return DB(cfg.database_url)


def _storage(cfg: Config):
    from .storage import R2
    return R2.from_config(cfg)


# ---- jobs ------------------------------------------------------------------------------
def cmd_publish(a, cfg: Config) -> int:
    from .publisher import JOB, Publisher
    db, alert = _db(cfg), Alerts.from_config(cfg)
    pub = Publisher(db, Instagram.from_config(cfg), _storage(cfg), alert)
    res = run_job(db, JOB, lambda: pub.run(force_slot=a.slot), alert)
    print(f"{res.outcome} {jsonable(res.detail) if res.detail else ''}".strip())
    return res.exit_code


def cmd_insights(a, cfg: Config) -> int:
    from .insights import JOB, InsightsPull
    db, alert = _db(cfg), Alerts.from_config(cfg)
    pull = InsightsPull(db, Instagram.from_config(cfg), alert)
    res = run_job(db, JOB, pull.run, alert)
    print(f"{res.outcome} {jsonable(res.detail) if res.detail else ''}".strip())
    return res.exit_code


# ---- controls ----------------------------------------------------------------------------
def cmd_db(a, cfg: Config) -> int:
    applied = _db(cfg).migrate()
    print("applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
    return OK


def cmd_pause(a, cfg: Config) -> int:
    _db(cfg).set_setting("paused", a.cmd == "pause")
    print("paused: every job stops at its next start" if a.cmd == "pause" else "resumed")
    return OK


def cmd_unstop(a, cfg: Config) -> int:
    db = _db(cfg)
    db.set_setting("stopped_jobs", [j for j in db.setting("stopped_jobs", []) if j != a.job])
    print(f"{a.job} will run again")
    return OK


def cmd_get(a, cfg: Config) -> int:
    print(jsonable(_db(cfg).setting(a.key)))
    return OK


def cmd_set(a, cfg: Config) -> int:
    _db(cfg).set_setting(a.key, json.loads(a.value))
    print(f"{a.key} = {a.value}")
    return OK


def cmd_status(a, cfg: Config) -> int:
    db = _db(cfg)
    tz = db.setting("timezone", "America/New_York")
    now = dt.datetime.now(UTC)
    day = schedule.local_day(now, tz)
    print(f"paused: {db.is_paused()}   stopped jobs: {db.setting('stopped_jobs', []) or 'none'}")
    print(f"today ({day}, {tz}):")
    for s in schedule.slots_on(day, db.setting("slot_times"), tz):
        r = db.one("select id, status, ig_media_id from reels where batch_date = %s and slot = %s "
                   "order by updated_at desc limit 1", (day, s.number))
        print(f"  slot {s.number} {s.at:%H:%M}  " + (f"{r['status']} {r['ig_media_id'] or ''} ({r['id']})" if r else "-"))
    n = db.one("select count(*) as n from reels where status = 'ready'")["n"]
    print(f"ready in queue: {n}")
    for r in db.q("select job, started_at, outcome, error from job_runs order by id desc limit 8"):
        print(f"  {r['started_at']:%Y-%m-%d %H:%M}Z {r['job']:<10} {r['outcome'] or 'running'} {r['error'] or ''}")
    return OK


def cmd_queue(a, cfg: Config) -> int:
    db = _db(cfg)
    key = a.video_key
    if a.file:
        key = f"reels/{dt.date.today():%Y/%m}/{uuid.uuid4().hex[:12]}.mp4"
        _storage(cfg).upload(Path(a.file), key)
        print(f"uploaded {a.file} -> r2://{cfg.r2_bucket}/{key}")
    if not key:
        raise ConfigError("give --file or --video-key")
    rid = db.add_reel(type=a.type, caption=a.caption, video_key=key, status="ready",
                      batch_date=dt.date.fromisoformat(a.date) if a.date else None, slot=a.slot,
                      hook_card=a.hook_card, source_asset_id=a.source_asset,
                      variables=json.loads(a.variables) if a.variables else {})
    print(f"queued reel {rid}")
    return OK


# ---- probe -------------------------------------------------------------------------------
def cmd_probe(a, cfg: Config) -> int:
    if a.what == "diff":
        lines = probe.diff(json.loads(Path(a.a).read_text()), json.loads(Path(a.b).read_text()))
        print("\n".join(lines) if lines else "no field changed")
        return OK
    ig = Instagram.from_config(cfg)
    if a.what == "account":
        print(jsonable(probe.account(ig)))
    elif a.what == "post":
        url = a.video_url
        if a.file:
            st = _storage(cfg)
            key = f"probe/{dt.datetime.now(UTC):%Y%m%d-%H%M%S}.mp4"
            st.upload(Path(a.file), key)
            url = st.get_url(key)
        if not url:
            raise ConfigError("give --file or --video-url")
        stf = None if a.share_to_feed is None else a.share_to_feed == "true"
        probe.post(ig, url, a.caption, strategy=a.strategy, share_to_feed=stf)
    elif a.what == "read":
        snap, path = probe.read(ig, a.media_id, a.label)
        print(probe.summary(snap))
        print(f"saved {path}")
    return OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jta-reels", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("db"); s.add_argument("action", choices=["migrate"]); s.set_defaults(fn=cmd_db)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("publish"); s.add_argument("--slot", type=int, choices=[1, 2, 3, 4],
                                                  help="post into today's slot N now, ignoring the clock")
    s.set_defaults(fn=cmd_publish)
    sub.add_parser("insights").set_defaults(fn=cmd_insights)
    sub.add_parser("pause").set_defaults(fn=cmd_pause)
    sub.add_parser("resume").set_defaults(fn=cmd_pause)
    s = sub.add_parser("unstop"); s.add_argument("job"); s.set_defaults(fn=cmd_unstop)
    s = sub.add_parser("get"); s.add_argument("key"); s.set_defaults(fn=cmd_get)
    s = sub.add_parser("set"); s.add_argument("key"); s.add_argument("value", help="JSON"); s.set_defaults(fn=cmd_set)

    s = sub.add_parser("queue")
    s.add_argument("--file"); s.add_argument("--video-key"); s.add_argument("--caption", required=True)
    s.add_argument("--type", choices=["remix", "new"], default="remix")
    s.add_argument("--date"); s.add_argument("--slot", type=int, choices=[1, 2, 3, 4])
    s.add_argument("--hook-card"); s.add_argument("--source-asset"); s.add_argument("--variables", help="JSON")
    s.set_defaults(fn=cmd_queue)

    s = sub.add_parser("probe"); ps = s.add_subparsers(dest="what", required=True)
    ps.add_parser("account")
    pp = ps.add_parser("post")
    pp.add_argument("--file"); pp.add_argument("--video-url"); pp.add_argument("--caption", required=True)
    pp.add_argument("--strategy", choices=GRADUATION_STRATEGIES, default="MANUAL")
    pp.add_argument("--share-to-feed", choices=["true", "false"], help="only to test Meta's behaviour; normally left out")
    pr = ps.add_parser("read"); pr.add_argument("media_id"); pr.add_argument("--label", default="snapshot")
    pd = ps.add_parser("diff"); pd.add_argument("a"); pd.add_argument("b")
    s.set_defaults(fn=cmd_probe)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a, Config.from_env())
    except ConfigError as e:
        print(f"config: {e}", file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
