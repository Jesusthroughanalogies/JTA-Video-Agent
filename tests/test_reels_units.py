"""Trial Reel Agent: pieces that need no database."""
import datetime as dt
import json

import pytest

from jta_reels import probe, schedule
from jta_reels.insights import to_row
from jta_reels.instagram import GraphError
from jta_reels.rules import caption_problems
from jta_reels.storage import presign_url
from reels_fakes import FakeGraph, make_ig

UTC = dt.timezone.utc
ET = "America/New_York"
SLOTS = ["08:00", "12:00", "16:00", "20:00"]


# ---- R2 signing ---------------------------------------------------------------------
def test_presign_matches_aws_published_example():
    # "Authenticating Requests: Using Query Parameters (AWS Signature Version 4)", example GET.
    url = presign_url("GET", "examplebucket.s3.amazonaws.com", "/test.txt", region="us-east-1",
                      access_key="AKIAIOSFODNN7EXAMPLE", secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                      expires=86400, now=dt.datetime(2013, 5, 24, tzinfo=UTC))
    assert url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404")
    assert "X-Amz-Credential=AKIAIOSFODNN7EXAMPLE%2F20130524%2Fus-east-1%2Fs3%2Faws4_request" in url


# ---- captions -------------------------------------------------------------------------
def test_caption_rules():
    good = "The first lie he'll tell you.\nSin isn't what you think.\nFollow for part 2\n#jesus #faith #bible #sin #christian"
    assert caption_problems(good) == []
    assert "caption contains an emoji" in caption_problems(good + " \U0001F64F")
    assert "caption contains an em or en dash" in caption_problems("Sin — missing the mark")
    assert any("link in bio" in p for p in caption_problems("Full video: link in bio"))
    assert any("hashtags" in p for p in caption_problems("x #a #b #c #d #e #f"))
    assert caption_problems("  ") == ["caption is empty"]


# ---- slots in US Eastern ------------------------------------------------------------------
def _at(y, m, d, h, mi=0):
    return dt.datetime(y, m, d, h, mi, tzinfo=UTC)


def test_slot_one_is_8am_eastern_in_winter_and_summer():
    # 9 Nov 2026 is EST (UTC-5): 08:00 ET = 13:00 UTC. In July (EDT, UTC-4) it's 12:00 UTC.
    assert [s.number for s in schedule.due_slots(_at(2026, 11, 9, 12, 59), SLOTS, ET)] == []
    assert [s.number for s in schedule.due_slots(_at(2026, 11, 9, 13, 5), SLOTS, ET)] == [1]
    assert [s.number for s in schedule.due_slots(_at(2027, 7, 1, 12, 5), SLOTS, ET)] == [1]


def test_evening_slot_runs_past_utc_midnight_and_catchup_window_closes():
    late = schedule.due_slots(_at(2026, 11, 10, 1, 30), SLOTS, ET)   # 20:30 ET on 9 Nov
    assert [(s.day, s.number) for s in late] == [(dt.date(2026, 11, 9), 4)]
    assert schedule.due_slots(_at(2026, 11, 9, 16, 30), SLOTS, ET) == []   # 11:30 ET: slot 1 window shut


def test_day_bounds_are_eastern_days():
    start, end = schedule.day_bounds_utc(dt.date(2026, 11, 9), ET)
    assert (start, end) == (_at(2026, 11, 9, 5), _at(2026, 11, 10, 5))


# ---- Graph API client ---------------------------------------------------------------------
def test_trial_reel_container_sends_trial_params_and_no_share_to_feed():
    g = FakeGraph()
    cid = make_ig(g).create_trial_reel("https://r2.test/a.mp4", "cap", strategy="MANUAL")
    method, path, params = g.calls[-1]
    assert (method, path, cid) == ("POST", "17841400000000000/media", "c1")
    assert params["media_type"] == "REELS"
    assert json.loads(params["trial_params"]) == {"graduation_strategy": "MANUAL"}
    assert "share_to_feed" not in params and "access_token" in params


def test_unknown_graduation_strategy_is_refused():
    with pytest.raises(ValueError):
        make_ig(FakeGraph()).create_trial_reel("u", "c", strategy="AUTO")


class Flaky:
    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    def request(self, method, url, params):
        self.calls += 1
        if self.calls <= self.failures:
            return 500, {"error": {"code": 2, "message": "temporary", "is_transient": True}}
        return 200, {"id": "x1"}


def test_get_is_retried_but_post_never_is():
    t = Flaky(2)
    ig = make_ig(t)
    assert ig.media("x1")["id"] == "x1" and t.calls == 3
    t2 = Flaky(1)
    with pytest.raises(GraphError) as e:
        make_ig(t2).publish("c1")
    assert e.value.transient and t2.calls == 1


def test_insights_fall_back_to_one_metric_at_a_time():
    g = FakeGraph()
    g.media["m1"] = {"id": "m1"}
    values, unsupported = make_ig(g).insights("m1", ["views", "likes", "follows", "ig_reels_avg_watch_time"])
    assert values == {"views": 4200, "likes": 100, "ig_reels_avg_watch_time": 12500}
    assert list(unsupported) == ["follows"]
    assert to_row(values) == {"views": 4200, "likes": 100, "avg_watch_s": 12.5}


def test_container_error_raises_with_meta_detail():
    g = FakeGraph()
    g.container_error = True
    ig = make_ig(g)
    cid = ig.create_trial_reel("u", "c")
    with pytest.raises(GraphError, match="ERROR"):
        ig.wait_until_ready(cid, poll=0)


# ---- Week 1 probe -------------------------------------------------------------------------------
def test_probe_diff_reports_the_graduation_field_not_the_counts():
    a = {"fields": {"is_shared_to_feed": {"ok": True, "value": False}, "like_count": {"ok": True, "value": 3}},
         "metrics": {"views": {"ok": True, "value": 10}, "follows": {"ok": False}}}
    b = {"fields": {"is_shared_to_feed": {"ok": True, "value": True}, "like_count": {"ok": True, "value": 9}},
         "metrics": {"views": {"ok": True, "value": 99}, "follows": {"ok": False}}}
    assert probe.diff(a, b) == ["field is_shared_to_feed: false -> true"]
