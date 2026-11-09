"""Postgres (Supabase) access. Every job reads and writes through here.

Use Supabase's direct connection string (port 5432), not the transaction pooler (6543):
the publisher holds a session advisory lock so two runs can never post at once.
"""
from __future__ import annotations

import contextlib
import datetime as dt
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SQL_DIR = Path(__file__).resolve().parent / "sql"
LIVE = ("publishing", "posted", "graduated", "shipped")


class DB:
    def __init__(self, url: str, *, search_path: str | None = None):
        kw = {"options": f"-c search_path={search_path}"} if search_path else {}
        self.conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, **kw)

    def close(self) -> None:
        self.conn.close()

    def q(self, sql: str, params: Any = None) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def one(self, sql: str, params: Any = None) -> dict | None:
        rows = self.q(sql, params)
        return rows[0] if rows else None

    # ---- migrations ---------------------------------------------------------
    def migrate(self) -> list[str]:
        self.q("create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())")
        done = {r["name"] for r in self.q("select name from schema_migrations")}
        applied = []
        for f in sorted(SQL_DIR.glob("*.sql")):
            if f.name in done:
                continue
            with self.conn.transaction():
                self.conn.execute(f.read_text())
                self.conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            applied.append(f.name)
        return applied

    # ---- settings -------------------------------------------------------------
    def setting(self, key: str, default: Any = None) -> Any:
        r = self.one("select value from settings where key = %s", (key,))
        return default if r is None else r["value"]

    def set_setting(self, key: str, value: Any) -> None:
        self.q("""insert into settings (key, value, updated_at) values (%s, %s, now())
                  on conflict (key) do update set value = excluded.value, updated_at = now()""", (key, Jsonb(value)))

    def is_paused(self) -> bool:
        return bool(self.setting("paused", False))

    # ---- locks and job runs -----------------------------------------------------
    @contextlib.contextmanager
    def lock(self, name: str) -> Iterator[bool]:
        """Session advisory lock. Yields False (without blocking) if another run holds it."""
        got = self.one("select pg_try_advisory_lock(hashtext(%s)) as ok", (name,))["ok"]
        try:
            yield got
        finally:
            if got:
                self.q("select pg_advisory_unlock(hashtext(%s))", (name,))

    def start_run(self, job: str) -> int:
        return self.one("insert into job_runs (job) values (%s) returning id", (job,))["id"]

    def finish_run(self, run_id: int, *, ok: bool, outcome: str, error: str | None = None,
                   detail: dict | None = None, cost_usd: float | None = None) -> None:
        self.q("""update job_runs set finished_at = now(), ok = %s, outcome = %s, error = %s,
                  detail = %s, cost_usd = %s where id = %s""",
               (ok, outcome, error, Jsonb(detail or {}), cost_usd, run_id))

    def last_runs(self, job: str, n: int = 2) -> list[dict]:
        return self.q("select * from job_runs where job = %s and finished_at is not null "
                      "order by started_at desc, id desc limit %s", (job, n))

    # ---- reels ------------------------------------------------------------------
    def add_reel(self, **f: Any) -> str:
        if "variables" in f:
            f["variables"] = Jsonb(f["variables"])
        cols = ", ".join(f)
        marks = ", ".join(["%s"] * len(f))
        return str(self.one(f"insert into reels ({cols}) values ({marks}) returning id", list(f.values()))["id"])

    def reel(self, reel_id: str) -> dict | None:
        return self.one("select * from reels where id = %s", (reel_id,))

    def update_reel(self, reel_id: str, **f: Any) -> None:
        sets = ", ".join(f"{k} = %s" for k in f)
        self.q(f"update reels set {sets}, updated_at = now() where id = %s", [*f.values(), reel_id])

    def in_flight(self) -> list[dict]:
        return self.q("select * from reels where status = 'publishing' order by updated_at")

    def slot_used(self, day: dt.date, slot: int) -> bool:
        return self.one("select 1 as x from reels where batch_date = %s and slot = %s and status = any(%s)",
                        (day, slot, list(LIVE))) is not None

    def live_between(self, start: dt.datetime, end: dt.datetime) -> int:
        """Reels posted (or being posted) in [start, end): what counts against the daily cap."""
        return self.one("""select count(*) as n from reels where status = any(%s)
                           and coalesce(posted_at, updated_at) >= %s and coalesce(posted_at, updated_at) < %s""",
                        (list(LIVE), start, end))["n"]

    def next_ready(self, day: dt.date, slot: int) -> dict | None:
        """The reel planned for this slot; otherwise the oldest ready reel from today or earlier."""
        return self.one("""select * from reels where status = 'ready' and video_key is not null
                           and (batch_date is null or batch_date <= %s)
                           order by (batch_date = %s and slot = %s) desc nulls last, created_at
                           limit 1""", (day, day, slot))

    def reels_for_insights(self, since: dt.datetime) -> list[dict]:
        return self.q("""select * from reels where ig_media_id is not null and posted_at >= %s
                         and status in ('posted', 'graduated', 'shipped') order by posted_at""", (since,))

    # ---- metrics ------------------------------------------------------------------
    def buckets_taken(self, reel_id: str) -> set[int]:
        return {r["at_hours"] for r in self.q("select at_hours from metrics where reel_id = %s", (reel_id,))}

    def add_metrics(self, reel_id: str, at_hours: int, age_hours: float, values: dict, raw: dict) -> None:
        cols = ["views", "reach", "likes", "comments", "shares", "saves", "follows",
                "profile_visits", "avg_watch_s", "total_watch_s", "is_shared_to_feed"]
        self.q(f"""insert into metrics (reel_id, at_hours, age_hours, {', '.join(cols)}, raw)
                   values (%s, %s, %s, {', '.join(['%s'] * len(cols))}, %s)
                   on conflict (reel_id, at_hours) do nothing""",
               [reel_id, at_hours, round(age_hours, 2), *[values.get(c) for c in cols], Jsonb(raw)])

    def add_check(self, reel_id: str, gate: str, passed: bool, notes: str = "") -> None:
        self.q("insert into checks (reel_id, gate, pass, notes) values (%s, %s, %s, %s)",
               (reel_id, gate, passed, notes))
