"""jta: run the JTA long-form pipeline.

  jta new ep001 --start-at ingest      create the episode state (phases before it count as done)
  jta run ep001                        start or continue from the last saved step
  jta resume ep001                     same as run (clears a pause)
  jta pause ep001                      ask a running process to stop cleanly
  jta status ep001                     where it is, what's done, credits used
  jta approve ep001 C                  approve a checkpoint (A topic, B script, C spend, D rough cut)
  jta approve-credits ep001 --extra 100   allow going past the 1,200-credit cap
  jta ledger ep001                     credit ledger totals and entries

Add --dry-run to any command to use the separate dry-run copy: no credits, no
Claude calls (add --with-llm to include Claude), checkpoints approve themselves.
Exit codes: 0 finished, 2 stopped cleanly (paused or waiting for a human), 1 error.
"""
from __future__ import annotations

import argparse
import getpass
import json
import shutil
import sys
import traceback

from . import store
from .config import Paths, Settings, load_dotenv
from .ledger import Ledger
from .pipeline import Pipeline, make_backends
from .runtime import Control, Log, Stop
from .state import PHASES, EpisodeState


def _episode_id(paths: Paths) -> str:
    if paths.shots.exists():
        for line in paths.shots.read_text().splitlines():
            if line.startswith("EPISODE_ID"):
                return line.split("=", 1)[1].strip().strip("\"'")
    return paths.episode


def cmd_new(a, paths: Paths) -> int:
    st = EpisodeState.create(paths.state, _episode_id(paths), "dry-run" if a.dry_run else "live", a.start_at)
    print(f"created {paths.state} (starting at {st.phase})")
    return 0


def cmd_run(a, paths: Paths) -> int:
    load_dotenv()
    cfg = Settings.for_mode(a.dry_run, max_new_jobs=a.max_new_jobs, max_in_flight=a.max_in_flight, until=a.until)
    if a.with_llm:
        cfg.use_llm = True
    if not paths.state.exists():
        if not a.dry_run:
            print(f"no state yet: run `jta new {paths.episode}` first", file=sys.stderr)
            return 1
        EpisodeState.create(paths.state, _episode_id(paths), "dry-run", a.start_at or "topic")
    log = Log(paths.events, quiet=a.quiet)
    control = Control(paths.control)
    with store.EpisodeLock(paths.lock):
        control.clear()                       # an explicit run/resume overrides an old pause
        control.install_signal_handlers()
        st = EpisodeState.load(paths.state)
        log("start", f"{st.data['episode_id']} ({'dry run' if a.dry_run else 'LIVE'}) resuming at "
                     f"{st.phase}: {st.summary()['jobs_done']}/{st.summary()['jobs_total']} jobs done")
        hf, voice = make_backends(paths)
        try:
            Pipeline(paths, cfg, st, hf, voice, control, log).run()
        except Stop as s:
            st.set_status(s.status, str(s))
            log(s.status, str(s))
            return 2
        except Exception as e:
            st.set_status("error", f"{type(e).__name__}: {e}")
            log("error", f"{type(e).__name__}: {e}")
            if a.verbose:
                traceback.print_exc()
            return 1
    return 0


def cmd_pause(a, paths: Paths) -> int:
    Control(paths.control).request_pause(getpass.getuser())
    print("pause requested; the running process stops after its current save. "
          f"Continue later with: jta resume {paths.episode}")
    return 0


def cmd_status(a, paths: Paths) -> int:
    st = EpisodeState.load(paths.state)
    t = Ledger(paths.ledger, Settings().credit_cap).totals()
    s = st.summary()
    if a.json:
        print(json.dumps({"summary": s, "credits": t, "checkpoints": st.data["checkpoints"]}, indent=2))
        return 0
    print(f"{st.data['episode_id']} [{st.data['mode']}]  phase: {s['phase']}  status: {s['status']}"
          + (f" ({st.data['status_reason']})" if st.data["status_reason"] else ""))
    print("phases: " + "  ".join(f"{p}:{st.data['phases'][p]['status']}" for p in PHASES))
    print("checkpoints: " + "  ".join(f"{k}:{'yes' if v['approved'] else 'no'}"
                                       for k, v in st.data["checkpoints"].items()))
    print(f"jobs: {s['jobs_done']}/{s['jobs_total']} done, {len(s['jobs_in_flight'])} in flight, "
          f"{len(s['jobs_pending'])} pending, {len(s['jobs_fallback'])} fallback")
    if s["jobs_in_flight"]:
        print("  in flight: " + ", ".join(s["jobs_in_flight"]))
    print(f"credits: {t['effective']:g} used of {t['cap']:g} cap (spent {t['spent']:g}, "
          f"reserved {t['open_reserved']:g}" + (f", balance drop {t['balance_drop']:g}" if t["balance_drop"] is not None else "") + ")")
    return 0


def cmd_approve(a, paths: Paths) -> int:
    st = EpisodeState.load(paths.state)
    st.approve(a.checkpoint.upper(), by=a.by, note=a.note or "")
    print(f"checkpoint {a.checkpoint.upper()} approved by {a.by}. Continue with: jta run {paths.episode}")
    return 0


def cmd_approve_credits(a, paths: Paths) -> int:
    Ledger(paths.ledger, Settings().credit_cap).raise_cap(a.extra, a.by)
    st = EpisodeState.load(paths.state)
    if st.status == "awaiting_credit_approval":
        st.set_status("running", "")
    print(f"cap raised by {a.extra:g} credits. Continue with: jta run {paths.episode}")
    return 0


def cmd_ledger(a, paths: Paths) -> int:
    lg = Ledger(paths.ledger, Settings().credit_cap)
    print(json.dumps(lg.totals(), indent=2))
    if a.entries:
        for e in store.read_jsonl(paths.ledger):
            print(json.dumps(e))
    return 0


def cmd_reset_dry_run(a, paths: Paths) -> int:
    d = Paths(paths.episode, True).base
    if d.exists():
        shutil.rmtree(d)
    print(f"removed {d}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jta", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("episode", help="folder under episodes/, e.g. ep001")
        p.add_argument("--dry-run", action="store_true")
        p.set_defaults(fn=fn)
        return p

    p = add("new", cmd_new)
    p.add_argument("--start-at", choices=PHASES, default="topic")
    for name in ("run", "resume"):
        p = add(name, cmd_run)
        p.add_argument("--max-new-jobs", type=int, help="canary: submit at most N new jobs, then stop")
        p.add_argument("--max-in-flight", type=int)
        p.add_argument("--with-llm", action="store_true", help="dry run but with real Claude calls")
        p.add_argument("--until", choices=PHASES, help="stop cleanly after this phase")
        p.add_argument("--start-at", choices=PHASES, help="dry run only: where a fresh dry run starts")
        p.add_argument("--quiet", action="store_true")
        p.add_argument("-v", "--verbose", action="store_true")
    add("pause", cmd_pause)
    p = add("status", cmd_status)
    p.add_argument("--json", action="store_true")
    p = add("approve", cmd_approve)
    p.add_argument("checkpoint", choices=list("ABCDabcd"))
    p.add_argument("--by", default=getpass.getuser())
    p.add_argument("--note")
    p = add("approve-credits", cmd_approve_credits)
    p.add_argument("--extra", type=float, required=True)
    p.add_argument("--by", default=getpass.getuser())
    p = add("ledger", cmd_ledger)
    p.add_argument("--entries", action="store_true")
    add("reset-dry-run", cmd_reset_dry_run)

    a = ap.parse_args(argv)
    try:
        return a.fn(a, Paths(a.episode, a.dry_run))
    except (FileNotFoundError, FileExistsError, store.LockedError) as e:
        print(f"jta: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
