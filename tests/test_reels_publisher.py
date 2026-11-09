"""Publisher and insights against a real Postgres and a fake Graph API.

Run with JTA_TEST_DATABASE_URL set (any Postgres 13+); skipped otherwise.
The point of these tests: no failure, at any moment, posts a reel twice.
"""
import datetime as dt

from jta_reels.db import DB
from jta_reels.insights import InsightsPull
from jta_reels.jobs import run_job
from jta_reels.publisher import Publisher
from reels_fakes import FakeGraph, FakeStorage, db, make_ig  # noqa: F401  (db is a fixture)

UTC = dt.timezone.utc
SLOT1 = dt.datetime(2026, 11, 9, 13, 5, tzinfo=UTC)      # 08:05 ET
SLOT2 = dt.datetime(2026, 11, 9, 17, 5, tzinfo=UTC)      # 12:05 ET
CAPTION = "Sin isn't a list of crimes.\nIt's an arrow that misses.\nFollow for part 2\n#jesus #sin #bible #faith #christian"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def setup(db, t=SLOT1):
    g, clock, alerts = FakeGraph(), Clock(t), []
    g.clock = clock
    pub = Publisher(db, make_ig(g), FakeStorage(), alerts.append, now=clock, poll=0)
    return g, clock, alerts, pub


def ready(db, caption=CAPTION, **kw):
    return db.add_reel(type="remix", caption=caption, video_key="reels/a.mp4", status="ready", **kw)


def test_nothing_due_before_the_slot(db):
    g, clock, alerts, pub = setup(db, t=SLOT1 - dt.timedelta(minutes=10))
    ready(db)
    assert pub.run().outcome == "skipped:nothing_due"
    assert g.calls == []


def test_posts_a_trial_reel_into_the_due_slot(db):
    g, clock, alerts, pub = setup(db)
    rid = ready(db)
    res = pub.run()
    assert res.outcome == "posted", res
    r = db.reel(rid)
    assert (r["status"], r["ig_media_id"], r["slot"], str(r["batch_date"])) == ("posted", "m1", 1, "2026-11-09")
    assert r["permalink"] == "https://instagram.com/reel/m1"
    create = [c for c in g.calls if c[1].endswith("/media") and c[0] == "POST"][0]
    assert '"MANUAL"' in create[2]["trial_params"] and create[2]["video_url"].startswith("https://r2.test/reels/a.mp4")


def test_a_slot_is_used_once(db):
    g, clock, alerts, pub = setup(db)
    ready(db), ready(db)
    assert pub.run().outcome == "posted"
    clock.t += dt.timedelta(minutes=10)
    assert pub.run().outcome == "skipped:nothing_due"
    clock.t = SLOT2
    assert pub.run().outcome == "posted"
    assert g.published_count() == 2


def test_daily_cap_in_eastern_days(db):
    g, clock, alerts, pub = setup(db)
    db.set_setting("daily_cap", 1)
    ready(db), ready(db)
    assert pub.run().outcome == "posted"
    clock.t = SLOT2
    assert pub.run().outcome == "skipped:daily_cap"
    assert g.published_count() == 1


def test_connection_drops_after_instagram_published_it(db):
    """The worst case: Meta posted the reel, we never heard back. The next run must adopt it, not repost."""
    g, clock, alerts, pub = setup(db)
    rid = ready(db)
    g.drop_after_publish = True
    res = run_job(db, "publisher", pub.run, alerts.append)
    assert not res.ok and db.reel(rid)["status"] == "publishing"
    clock.t += dt.timedelta(minutes=10)
    res = run_job(db, "publisher", pub.run, alerts.append)
    assert res.outcome == "posted", res
    assert db.reel(rid)["ig_media_id"] == "m1"
    assert g.published_count() == 1
    assert not [c for c in g.calls if c[1].endswith("media_publish")][1:], "media_publish was called again"


def test_connection_drops_before_publish_reached_instagram(db):
    g, clock, alerts, pub = setup(db)
    rid = ready(db)
    g.drop_before_publish = True
    assert not pub.run().ok
    clock.t += dt.timedelta(minutes=10)
    assert pub.run().outcome == "posted"
    assert db.reel(rid)["ig_media_id"] == "m1" and g.published_count() == 1


def test_container_error_marks_the_reel_failed(db):
    g, clock, alerts, pub = setup(db)
    rid = ready(db)
    g.container_error = True
    res = run_job(db, "publisher", pub.run, alerts.append)
    assert res.outcome == "failed_publish"
    assert db.reel(rid)["status"] == "failed_publish" and "2207026" in db.reel(rid)["status_note"]
    assert any("publisher failed" in a for a in alerts)


def test_bad_caption_is_blocked_and_the_next_reel_goes_out(db):
    g, clock, alerts, pub = setup(db)
    bad = ready(db, caption="Watch this \U0001F525 link in bio")
    good = ready(db)
    assert pub.run().outcome == "posted"
    assert db.reel(bad)["status"] == "failed_check" and db.reel(good)["status"] == "posted"


def test_planned_slot_reel_goes_first(db):
    g, clock, alerts, pub = setup(db)
    backlog = ready(db)
    planned = ready(db, batch_date=dt.date(2026, 11, 9), slot=1)
    pub.run()
    assert db.reel(planned)["status"] == "posted" and db.reel(backlog)["status"] == "ready"


def test_no_reel_alerts_once_per_slot(db):
    g, clock, alerts, pub = setup(db)
    for _ in range(3):
        run_job(db, "publisher", pub.run, alerts.append)
        clock.t += dt.timedelta(minutes=10)
    assert len([a for a in alerts if "no reel is ready" in a]) == 1


def test_kill_switch(db):
    g, clock, alerts, pub = setup(db)
    ready(db)
    db.set_setting("paused", True)
    assert run_job(db, "publisher", pub.run, alerts.append).outcome == "skipped:paused"
    assert g.calls == []


def test_two_failures_in_a_row_stop_the_job(db):
    g, clock, alerts, pub = setup(db)
    g.container_error = True
    ready(db), ready(db), ready(db)
    run_job(db, "publisher", pub.run, alerts.append)
    clock.t = SLOT2
    run_job(db, "publisher", pub.run, alerts.append)
    assert db.setting("stopped_jobs") == ["publisher"]
    assert any("failed twice" in a for a in alerts)
    clock.t += dt.timedelta(hours=4)
    assert run_job(db, "publisher", pub.run, alerts.append).outcome == "skipped:stopped"


def test_a_second_publisher_waits_its_turn(db):
    g, clock, alerts, pub = setup(db)
    ready(db)
    other = DB(db.conn.info.dsn)
    try:
        with other.lock("jta-reels:publisher") as got:
            assert got
            assert pub.run().outcome == "skipped:locked"
    finally:
        other.close()


# ---- insights ----------------------------------------------------------------------------------
def test_insights_snapshots_by_bucket_and_learn_unsupported_metrics(db):
    g, clock, alerts, pub = setup(db)
    rid = ready(db)
    pub.run()
    pull = InsightsPull(db, make_ig(g), alerts.append, now=clock)

    clock.t = SLOT1 + dt.timedelta(hours=7)
    assert pull.run().detail["snapshots"] == 1
    clock.t = SLOT1 + dt.timedelta(hours=50)                  # 24 h pull was missed: file it under 48
    assert pull.run().detail["snapshots"] == 1
    rows = db.q("select at_hours, age_hours, views, likes, follows, avg_watch_s, is_shared_to_feed "
                "from metrics where reel_id = %s order by at_hours", (rid,))
    assert [r["at_hours"] for r in rows] == [6, 48]
    assert float(rows[1]["age_hours"]) == 50.0
    assert (rows[1]["views"], rows[1]["likes"], rows[1]["follows"]) == (4200, 100, None)
    assert float(rows[1]["avg_watch_s"]) == 12.5 and rows[1]["is_shared_to_feed"] is False
    assert db.setting("insights_unsupported") == ["follows"]
    assert len([a for a in alerts if "follows" in a]) == 1
    assert pull.run().detail["snapshots"] == 0


def test_graduation_read_from_is_shared_to_feed_once_switched_on(db):
    g, clock, alerts, pub = setup(db)
    rid = ready(db)
    pub.run()
    g.shared_to_feed["m1"] = True
    pull = InsightsPull(db, make_ig(g), alerts.append, now=clock)
    clock.t = SLOT1 + dt.timedelta(hours=7)
    pull.run()
    assert db.reel(rid)["status"] == "posted"                 # default signal is Matt's answer
    db.set_setting("graduation_signal", "is_shared_to_feed")
    clock.t = SLOT1 + dt.timedelta(hours=25)
    pull.run()
    assert db.reel(rid)["status"] == "graduated"
