"""Stop/restart tests: kill the agent mid-generation and prove nothing is generated twice.

Each test drives the real CLI (python -m jta_agent ... --dry-run) in a
subprocess against the fake Higgsfield, whose job list lives on disk like the
real server's. After every test, audit() checks the server side:
  - every job on the server is tracked in state.json exactly once
  - each prompt was generated exactly as often as the plan (plus recorded redos) needs
  - the ledger's spend equals what the server charged
"""
import collections
import json
import time
from pathlib import Path

import pytest

from conftest import ROOT, Run, kill9

PLAN = json.loads((ROOT / "episodes" / "ep001" / "generation_plan.json").read_text())
PLAN_COUNT = collections.Counter(s["params"]["prompt"] for s in PLAN["steps"])
PLAN_CREDITS = sum(s["credits"] for s in PLAN["steps"])
PLAN_JOBS = len(PLAN["steps"])  # derived from the plan, so the tests follow the shot list


def audit(r: Run, allow_redos: bool = False) -> dict:
    st = r.state()
    server = r.server_jobs()
    tracked = collections.Counter(a["job_id"] for j in st["jobs"].values()
                                  for a in j["attempts"] if a.get("job_id"))
    server_ids = [j["id"] for j in server]

    assert len(server_ids) == len(set(server_ids))
    untracked = set(server_ids) - set(tracked)
    assert not untracked, f"jobs on the server that the agent lost track of: {untracked}"
    assert all(n == 1 for n in tracked.values()), "a job id is used by two attempts"
    assert all(j["status"] in ("done", "fallback") for j in st["jobs"].values())

    per_prompt = collections.Counter(j["params"]["prompt"] for j in server)
    if allow_redos:
        # extra generations are allowed only as recorded redo attempts (QC reject or server failure)
        redo = collections.Counter()
        for j in st["jobs"].values():
            used = [a for a in j["attempts"] if a.get("job_id")]
            if used:
                redo[used[0]["prompt"]] += len(used) - 1
        for prompt, n in per_prompt.items():
            assert n == PLAN_COUNT[prompt] + redo[prompt], prompt[:60]
        assert all(len([a for a in j["attempts"] if a.get("job_id")]) <= 3 for j in st["jobs"].values())
    else:
        assert per_prompt == PLAN_COUNT, "some prompt was generated more (or less) often than planned"

    charged = sum(8.75 if j["tool"] == "generate_video" else 2.0 for j in server)
    ledger = json.loads(r.other("ledger").stdout)
    assert abs(ledger["spent"] - charged) < 1e-6, (ledger, charged)
    assert ledger["open_reserved"] == 0
    return {"server_jobs": len(server), "charged": charged, "ledger": ledger}


def test_clean_run_matches_plan(runner):
    r = runner.run()
    assert r.returncode == 2, r.stdout  # 2 = stopped cleanly after --until generate
    a = audit(runner)
    assert a["server_jobs"] == PLAN_JOBS and a["charged"] == PLAN_CREDITS


def test_kill_mid_generation_then_restart(runner):
    p = runner.start()
    runner.wait_for(lambda: len(runner.server_jobs()) >= 12 and runner.state()["summary"]["jobs_in_flight"])
    kill9(p)                                               # pull the plug, no cleanup
    before = runner.state()
    in_flight = before["summary"]["jobs_in_flight"]
    submitted_before = {k for k, j in before["jobs"].items() if any(a.get("job_id") for a in j["attempts"])}
    server_before = len(runner.server_jobs())
    assert in_flight, "the kill should land while jobs are rendering"
    time.sleep(2.5)                                        # in-flight jobs finish on the server while we're dead

    r = runner.run()
    assert r.returncode == 2, r.stdout
    a = audit(runner)
    assert a["server_jobs"] == PLAN_JOBS

    # Second run: nothing that already had a job id was submitted again; it was collected.
    second_run = _events_after_last_start(runner)
    resubmitted = {e["msg"].split()[0] for e in second_run if e["event"] == "submitted"} & submitted_before
    assert not resubmitted, f"submitted again after restart: {resubmitted}"
    collected = {e["msg"].split(":")[0] for e in second_run if e["event"] == "done"}
    assert set(in_flight) <= collected, "jobs in flight at the kill should be collected on restart"
    print(f"\nkilled with {server_before} jobs on the server, {len(in_flight)} in flight; "
          f"restart collected them and finished with {a['server_jobs']} jobs total, {a['charged']} credits")


def test_crash_between_submit_and_saving_the_job_id(runner):
    # The worst moment: Higgsfield has created job #7, but we die before writing its id down.
    r = runner.run(JTA_CRASH_AFTER_SUBMITS="7")
    assert r.returncode == 137
    st = runner.state()
    stuck = [k for k, j in st["jobs"].items() if j["status"] == "submitting"]
    assert len(stuck) == 1 and len(runner.server_jobs()) == 7

    r = runner.run()
    assert r.returncode == 2, r.stdout
    events = _events_after_last_start(runner)
    assert any(e["event"] == "reconciled" and stuck[0] in e["msg"] and "adopted" in e["msg"] for e in events)
    a = audit(runner)
    assert a["server_jobs"] == PLAN_JOBS


def test_pause_and_resume(runner):
    p = runner.start()
    runner.wait_for(lambda: len(runner.server_jobs()) >= 8)
    assert runner.other("pause").returncode == 0
    out, _ = p.communicate(timeout=60)
    assert p.returncode == 2
    st = runner.state()
    assert st["status"] == "paused" and st["summary"]["jobs_done"] < PLAN_JOBS
    assert "paused" in runner.other("status").stdout

    r = runner.run()                       # resume: carries on from the saved step
    assert r.returncode == 2
    assert audit(runner)["server_jobs"] == PLAN_JOBS


def test_wifi_drop_and_return(runner, tmp_path):
    offline = tmp_path / "offline"
    p = runner.start(JTA_FAKE_OFFLINE_FILE=str(offline))
    runner.wait_for(lambda: len(runner.server_jobs()) >= 6)
    offline.touch()                        # wifi goes
    runner.wait_for(lambda: any(e["event"] == "offline" for e in runner.events()))
    time.sleep(3)
    offline.unlink()                       # wifi comes back
    p.communicate(timeout=120)
    assert p.returncode == 2
    kinds = [e["event"] for e in runner.events()]
    assert "offline" in kinds and "online" in kinds
    assert audit(runner)["server_jobs"] == PLAN_JOBS


def test_long_outage_pauses_then_resume(runner, tmp_path):
    offline = tmp_path / "offline"
    p = runner.start(JTA_FAKE_OFFLINE_FILE=str(offline), JTA_OFFLINE_PATIENCE="2")
    runner.wait_for(lambda: len(runner.server_jobs()) >= 6)
    offline.touch()
    p.communicate(timeout=60)
    st = runner.state()
    assert p.returncode == 2 and st["status"] == "paused" and "no connection" in st["status_reason"]
    offline.unlink()
    r = runner.run()
    assert r.returncode == 2
    assert audit(runner)["server_jobs"] == PLAN_JOBS


def test_redos_and_failures_survive_a_kill(runner):
    env = {"JTA_FAKE_QC_REJECT_RATE": "0.25", "JTA_FAKE_FAIL_RATE": "0.1"}
    p = runner.start(**env)
    runner.wait_for(lambda: len(runner.server_jobs()) >= 15)
    kill9(p)
    r = runner.run(**env)
    assert r.returncode == 2, r.stdout
    a = audit(runner, allow_redos=True)
    st = runner.state()
    attempts = sum(1 for j in st["jobs"].values() for a_ in j["attempts"] if a_.get("job_id"))
    assert a["server_jobs"] == attempts > PLAN_JOBS      # redos happened, each one recorded
    assert any(e["event"] == "qc-reject" for e in runner.events())


def test_two_processes_cannot_run_one_episode(runner):
    p = runner.start()
    runner.wait_for(lambda: (runner.base / "state.json").exists() and len(runner.server_jobs()) >= 1)
    second = runner.run(timeout=30)
    assert second.returncode == 1 and "already running" in second.stdout
    p.communicate(timeout=120)
    assert audit(runner)["server_jobs"] == PLAN_JOBS


def _events_after_last_start(r: Run) -> list[dict]:
    ev = r.events()
    last = max(i for i, e in enumerate(ev) if e["event"] == "start")
    return ev[last:]
