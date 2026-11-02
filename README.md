# JTA long-form video agent

The production agent for Jesus Through Analogies, built on the Claude Agent SDK
(Python). It runs the 8 phases in `claude/video-agent-system-prompt.md`, stops at
checkpoints A to D for Matt and Jack, and is safe to kill at any moment: run it
again and it carries on from the last saved step without generating anything twice.

## What's where

| Path | What it is |
|---|---|
| `claude/video-agent-system-prompt.md` | The system prompt. Sections 5 (visuals) and 6 (voice) are locked and override everything else. |
| `knowledge/` | Style bible, script rules, compliance, learnings, performance log, episode notes. Loaded into Claude's system prompt every run. |
| `jta_visuals/` | Locked visual rules as code: prompt builder, validator, credit planner, grade filter. Used as delivered. |
| `episodes/ep001/` | `shots.py` (shot list), `generation_plan.json` (planner output), `script.md` (export of the script doc, rev 57). |
| `jta_agent/` | The agent: pipeline, generation executor, ledger, state, voice, Claude steps, CLI. |
| `tests/` | Rules tests, unit tests, and the kill/restart tests. |

## Setup (on the machine that will run it)

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env                       # fill in keys and voice ids; never committed
cp mcp_servers.example.json mcp_servers.json   # Drive + ElevenLabs MCP for Claude; never committed
```

Needs ffmpeg, the cairo library (`brew install cairo` or `apt install libcairo2-dev`) for the
animation renderer `jta_anim`, Python 3.11+, and Claude access for the Agent SDK (an API key in `.env`
or a logged-in `claude` CLI).

## Commands

```bash
jta new ep001 --start-at ingest    # ep001's topic and script are done; start at voiceover/ingest
jta run ep001                      # start, or continue from the last saved step
jta status ep001                   # phase, jobs done / in flight / pending, credits used
jta approve ep001 C                # approve a checkpoint (A topic, B script, C spend, D rough cut)
jta pause ep001                    # ask the running process to stop cleanly
jta resume ep001                   # carry on (same as run)
jta approve-credits ep001 --extra 100   # allow going past the 1,200-credit cap
jta ledger ep001 --entries         # every credit movement
jta run ep001 --until shotlist     # stop after a phase, e.g. to see the cost before approving C
jta run ep001 --max-new-jobs 1     # canary: one real Higgsfield job, then stop for a look
```

Exit codes: 0 finished, 2 stopped cleanly (paused, waiting for approval, or offline), 1 error.

## How stopping and restarting works

- **State after every step.** `episodes/<id>/state.json` records the phase, each step
  that's finished, and every Higgsfield job with all its attempts and job IDs. It's
  rewritten atomically (temp file, then rename), so a kill never leaves it half-written.
- **Job IDs saved before polling.** For every generation the agent saves "about to
  submit", reserves the credits, submits, saves the job ID, and only then starts
  polling. On restart, any job with a saved ID is collected, never submitted again.
- **The dangerous gap is covered.** If the process dies after Higgsfield creates a job
  but before the ID is saved, the restart finds that job in Higgsfield's history by its
  exact prompt and adopts it. It only resubmits if, after a settling time, no
  matching job exists.
- **Finished work is never redone.** Downloads and QC results are saved before a job is
  marked done. Finished voice lines are skipped unless their script line changed.
- **Credit ledger with a hard cap.** `ledger.jsonl` is append-only. Credits are reserved
  before every submit and the cap is checked first. An unconfirmed reservation counts
  as spent until proven otherwise. The check uses whichever is larger: the ledger, or the
  drop in your real Higgsfield balance. At 1,200 the agent stops and tells you the exact
  `approve-credits` command.
- **Spend needs Checkpoint C.** Nothing is generated until `jta approve <ep> C`, and
  starting an episode at a later phase never counts as approval.
- **Wifi drops.** Status checks retry with backoff. After 30 minutes offline the agent
  pauses with everything saved; `jta resume` picks it up.
- **One process per episode.** An OS lock prevents two runs at once. The OS releases
  it when a process dies, even after `kill -9`.
- **Pause.** `jta pause`, Ctrl-C or SIGTERM all stop cleanly. Jobs already submitted
  keep rendering on Higgsfield and are collected on resume.

## Dry run

Add `--dry-run` to any command. It runs all 8 phases against a fake Higgsfield and
fake voices. No credits are spent and Claude isn't called (add `--with-llm` to include
Claude). Checkpoints approve themselves, and everything goes in
`episodes/<id>/dryrun/`, so real state is never touched. It still runs the real
planner, the real ledger and cap, real ffmpeg grading and a real rough cut, captions
and upload pack.

```bash
jta run ep001 --dry-run            # whole pipeline, about a minute
jta reset-dry-run ep001
```

## Tests

```bash
.venv/bin/python -m pytest -v
```

`tests/test_resilience.py` drives the real CLI and kills it:
- **kill -9 mid-generation:** restart collects the jobs that were rendering.
- **kill right after Higgsfield accepts a job but before its ID is saved:** restart adopts it from history.
- **pause/resume:** stops cleanly and carries on.
- **wifi drop and return, and a long outage:** pauses, then resumes.
- **QC rejects and server failures, then a kill.**
- **a second process on the same episode:** refused.

After each, it audits the fake server. Every job must be tracked exactly once, each
prompt generated exactly as often as planned (plus recorded redos), and the ledger
must equal what was charged.

## Tools from the kit README: what's in, what's missing

| Tool | Status |
|---|---|
| File system, shell, web search and fetch | In (Agent SDK built-ins) |
| jta_anim (pycairo) | In: every [ANIM] and [TEXT] shot, drawn in code (system prompt 5.5); preview with `python -m jta_anim.scenes_ep001 OUT_DIR` |
| ffmpeg | In: QC frames, the locked grade, rough cut and final render, loudness to -14 LUFS |
| Image check | In: start, middle and end frames from every clip, checked by Claude |
| Higgsfield | In (`jta_agent/higgsfield.py`). Status, history, balance and cost checks are built from real replies. The reply to a paid submit hasn't been seen yet, so use `--max-new-jobs 1` the first time. Anything it can't read is resolved from history, never resubmitted. Needs `HIGGSFIELD_MCP_URL` and `HIGGSFIELD_MCP_TOKEN`. |
| ElevenLabs voice clones | In (`jta_agent/voice.py`, REST text-to-speech). Not yet run against the live API: listen to the first part before doing the rest. |
| ElevenLabs speech-to-text | Through Claude with the ElevenLabs MCP in `mcp_servers.json` |
| **ElevenLabs music and sound effects** | **Missing.** Phase 5 step 4 has no step yet, and the restricted ElevenLabs connector can't make music. Needs the full connector or the music API. |
| **Animation renderer** | **Missing.** [ANIM] and [TEXT] shots are plain cards. Claude is asked to render them, but there's no reusable renderer (Remotion or Python) yet. |
| Google Drive | Through Claude with a Drive MCP in `mcp_servers.json`. Moving large video files over MCP is unproven: test with the rough cut early. |
| **YouTube Data API** | **Missing.** The system prompt's Phase 7 says to upload as private. For now the agent writes the upload pack (video, captions, `upload.md` with both disclosure lines) and you upload it. |
| **YouTube Analytics API** | **Missing.** The 48-hour and 7-day pulls in Phase 8 step 3 aren't built. |
| **Messaging** | **Missing.** Checkpoints print to the terminal and wait for `jta approve`. There's no phone notification yet. |
