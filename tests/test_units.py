"""Unit tests: parsing real Higgsfield replies, the ledger, the cap, the C gate, voice rules, storage."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ROOT
from jta_agent import higgsfield as H
from jta_agent import store
from jta_agent.config import Paths, Settings
from jta_agent.dryrun import FakeBackend
from jta_agent.generate import Generator
from jta_agent.ledger import CapReached, Ledger
from jta_agent.pipeline import Pipeline
from jta_agent.runtime import Control, Log, NeedsApproval, NeedsCredits
from jta_agent.state import EpisodeState
from jta_agent.voice import FakeVoice, parse_script

# ---- replies captured from the real Higgsfield MCP on 2 Nov 2026 ---------------
REAL_COST = {"cost": {"credits": 8.75, "credits_exact": 8.75}}
REAL_WAIT = {"jobs": [
    {"index": 0, "job_id": "10260372-5958-42e8-900d-f51448c2d4f5", "status": "completed", "type": "image",
     "model": "gpt_image_2_5", "result_url": "https://d8j0ntlcm91z4.cloudfront.net/x.png"},
    {"index": 1, "job_id": "fa0e0ad5-a639-4f8e-be9a-3118411b1a5e", "status": "completed", "type": "video",
     "model": "kling3_0", "result_url": "https://d8j0ntlcm91z4.cloudfront.net/y.mp4"}],
    "summary": {"total": 2, "completed": 2, "failed": 0, "active": 0, "errors": 0}, "all_terminal": True}
REAL_HISTORY = {"items": [{"id": "bff4ebb7-f185-4464-96e3-8b8658d884f4", "type": "video", "status": "completed",
                           "model": "kling3_0", "params": {"prompt": "Slow dolly forward through a doorway."},
                           "results": {"rawUrl": "https://x/y.mp4"}, "createdAt": 1793591320.153481}],
                "next_cursor": 1793591320.153481}


def test_parse_real_replies():
    assert H.parse_cost(REAL_COST) == 8.75
    w = H.parse_wait(REAL_WAIT)
    assert w["fa0e0ad5-a639-4f8e-be9a-3118411b1a5e"].state == "completed"
    assert w["fa0e0ad5-a639-4f8e-be9a-3118411b1a5e"].result_url.endswith(".mp4")
    items, cursor = H.parse_history(REAL_HISTORY)
    assert items[0].prompt == "Slow dolly forward through a doorway." and items[0].created_at > 1.7e9


def test_parse_submit_shapes():
    jid = "50696b91-d02b-40a4-93f3-60e4b9c9b711"
    assert H.parse_submit({"job_id": jid}).job_ids == [jid]
    assert H.parse_submit({"jobs": [{"id": jid, "status": "queued"}]}).job_ids == [jid]
    p = H.parse_submit({"recommended_preset": {"id": "preset-123", "name": "x"}})
    assert p.job_ids == [] and p.preset_id == "preset-123"
    assert H.parse_submit({"recovery_tool": "models_explore"}).needs_human
    assert H.parse_submit({"text": "something new"}).job_ids == []   # -> treated as unknown, reconciled


def test_ledger_counts_open_reserves_and_cap(tmp_path):
    lg = Ledger(tmp_path / "l.jsonl", 20)
    lg.reserve("a", 1, 8.75)
    assert lg.totals()["committed"] == 8.75          # unconfirmed reserve counts as spent
    lg.submitted("a", 1, "j1", 8.75)
    lg.reserve("b", 1, 8.75)
    lg.void("b", 1, "not created")
    assert lg.totals()["committed"] == 8.75
    lg.check(8.75, "c")                               # 17.5 <= 20
    with pytest.raises(CapReached):
        lg.check(17.5, "d")
    lg.raise_cap(50, "matt")
    lg.check(17.5, "d")
    lg.balance(100)
    lg.balance(60)                                    # real balance dropped 40, more than the ledger
    assert lg.totals()["effective"] == 40


def test_torn_log_line_is_ignored(tmp_path):
    f = tmp_path / "x.jsonl"
    store.append_jsonl(f, {"a": 1})
    with open(f, "a") as fh:
        fh.write('{"a": 2, "b"')                       # killed mid-write
    assert list(store.read_jsonl(f)) == [{"a": 1}]


def test_lock_is_released_when_the_holder_is_killed(tmp_path):
    lock = tmp_path / ".lock"
    code = f"import time,sys; sys.path.insert(0,{str(ROOT)!r}); from jta_agent.store import EpisodeLock\n" \
           f"l=EpisodeLock(__import__('pathlib').Path({str(lock)!r})).__enter__(); print('held',flush=True); time.sleep(60)"
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    with pytest.raises(store.LockedError):
        store.EpisodeLock(lock).__enter__()
    p.kill()
    p.wait()
    with store.EpisodeLock(lock):
        pass


def _gen(episode: str, cap: float):
    paths = Paths(episode, dry_run=True)
    st = EpisodeState.create(paths.state, "t", "dry-run", "generate")
    cfg = Settings.for_mode(True, credit_cap=cap)
    hf = FakeBackend(paths.base)
    hf.job_seconds = 0
    g = Generator(paths, st, Ledger(paths.ledger, cap), hf, lambda *a: (True, "ok"), Control(paths.control),
                  Log(paths.events, quiet=True), cfg)
    return g, paths, hf


def test_credit_cap_stops_and_asks(episode):
    g, paths, hf = _gen(episode, cap=40)
    with pytest.raises(NeedsCredits) as e:
        g.run()
    assert "jta approve-credits" in str(e.value)
    spent = sum(8.75 if j["tool"] == "generate_video" else 2 for j in hf.server_jobs())
    assert spent <= 40                                   # never went over
    g.ledger.raise_cap(1000, "test")
    g.run()                                              # carries on after approval
    assert len(hf.server_jobs()) == 42


def test_no_credits_before_checkpoint_c(episode):
    paths = Paths(episode, dry_run=False)                # live-mode rules
    st = EpisodeState.create(paths.state, "t", "live", "generate")

    class NoSpend(FakeBackend):
        def submit(self, *a, **k):
            raise AssertionError("tried to spend before Checkpoint C")

    cfg = Settings.for_mode(False)
    pipe = Pipeline(paths, cfg, st, NoSpend(paths.base / "fake"), FakeVoice(), Control(paths.control),
                    Log(paths.events, quiet=True))
    with pytest.raises(NeedsApproval) as e:
        pipe.run()
    assert "C" in str(e.value)


def test_voice_lines_follow_section_6(tmp_path):
    lines = parse_script(ROOT / "episodes" / "ep001" / "script.md")
    assert len(lines) == 72
    assert {l.speaker for l in lines} == {"MATT", "JACK"}
    assert not any("own words" in l.text or l.part == "story" for l in lines)   # story is never cloned
    assert not any("(music" in l.text or "(pause)" in l.text for l in lines)
    bad = tmp_path / "s.md"
    bad.write_text("## Part 1: x\n\n| # | Words | Visual |\n|---|---|---|\n| 1 | **MATT or JACK:** hi | [AI] x |\n")
    with pytest.raises(ValueError):
        parse_script(bad)


def test_blocked_tools_for_claude():
    from jta_agent.llm import BLOCKED_TOOLS, ENV_FILE
    assert BLOCKED_TOOLS.search("mcp__Higgsfield__generate_video")
    assert BLOCKED_TOOLS.search("mcp__higgsfield__generate_image_batch")
    assert BLOCKED_TOOLS.search("mcp__ElevenLabs__creative_generate_speech")
    assert not BLOCKED_TOOLS.search("mcp__ElevenLabs__creative_transcribe_audio")
    assert not BLOCKED_TOOLS.search("mcp__google_drive__download_file_content")
    assert ENV_FILE.search('{"file_path": "/repo/.env"}') and ENV_FILE.search("cat .env.local")
