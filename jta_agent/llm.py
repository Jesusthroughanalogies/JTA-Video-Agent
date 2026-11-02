"""Claude (Agent SDK) for the thinking parts: topic, script, alignment, QC, packaging.

The system prompt is claude/video-agent-system-prompt.md exactly as written
(Sections 5 and 6 are locked), followed by the knowledge base and a short
runtime note about how this program works.

Guards that apply whatever the model decides (PreToolUse hooks):
- no Higgsfield generation tools: every credit goes through the ledger
- no ElevenLabs speech or voice-design tools: the clones only ever say
  approved script lines, through voice.py
- no reading .env files
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from .config import KNOWLEDGE_DIR, REPO, SYSTEM_PROMPT_FILE

BLOCKED_TOOLS = re.compile(
    r"^mcp__.*higgsfield.*__(generate|execute_preset|ai_influencer_generate|upscale|outpaint|reframe|"
    r"motion_control|dubbing|voice_change|create_voice)"
    r"|^mcp__.*eleven.*__(creative_generate_speech|creative_design_voice|creative_save_designed_voice|"
    r"creative_generate_in_flow|creative_run_flow_nodes)",
    re.I,
)
ENV_FILE = re.compile(r"(^|[/\s'\"=])\.env(\.[\w-]+)?($|[\s'\";|&>)])")

RUNTIME_NOTE = """

---

## Runtime note (from the jta_agent program, not part of the locked prompt)

- You run one step of the pipeline at a time. The program saves state, runs every
  checkpoint, and talks to Higgsfield itself. You have no Higgsfield generation tools:
  write shots in episodes/<id>/shots.py and the program generates them within the
  1,200-credit ledger.
- Voice clone generation is also done by the program from the approved script. You
  have no speech-generation tools. Never try to make the clones say anything.
- Write each step's output to the exact path you are given. The program checks it.
- Never read or print any .env file.
"""


def system_prompt() -> str:
    parts = [SYSTEM_PROMPT_FILE.read_text(), RUNTIME_NOTE, "\n---\n\n# Knowledge base (loaded at start of run)\n"]
    for f in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        parts.append(f"\n## File: knowledge/{f.relative_to(KNOWLEDGE_DIR)}\n\n{f.read_text()}\n")
    return "".join(parts)


def mcp_servers() -> dict:
    """Remote MCP servers for Claude (Google Drive, ElevenLabs speech-to-text...).

    Read from mcp_servers.json (git-ignored; copy mcp_servers.example.json).
    """
    p = Path(os.environ.get("JTA_MCP_SERVERS", REPO / "mcp_servers.json"))
    return json.loads(p.read_text()) if p.exists() else {}


async def _guard(input_data: dict, tool_use_id: Optional[str], context: Any) -> dict:
    name = input_data.get("tool_name", "")
    args = json.dumps(input_data.get("tool_input", {}))
    reason = None
    if BLOCKED_TOOLS.search(name):
        reason = f"{name} is blocked: generation runs in the program so credits and voice rules are enforced."
    elif ENV_FILE.search(args):
        reason = ".env files are off limits."
    if reason:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny", "permissionDecisionReason": reason}}
    return {}


def _options(extra_tools: list[str] | None = None, output_schema: dict | None = None, max_turns: int = 40):
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    servers = mcp_servers()
    tools = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "WebFetch"] + (extra_tools or [])
    tools += [f"mcp__{name}" for name in servers]
    kw: dict = dict(
        system_prompt=system_prompt(),
        cwd=str(REPO),
        allowed_tools=tools,
        mcp_servers=servers,
        permission_mode="acceptEdits",
        max_turns=max_turns,
        setting_sources=[],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_guard])]},
    )
    if os.environ.get("JTA_MODEL"):
        kw["model"] = os.environ["JTA_MODEL"]
    if output_schema:
        kw["output_format"] = {"type": "json_schema", "schema": output_schema}
    return ClaudeAgentOptions(**kw)


async def _run(task: str, options) -> tuple[str, Any, float]:
    from claude_agent_sdk import ResultMessage, query

    text, structured, cost = "", None, 0.0
    async for msg in query(prompt=task, options=options):
        if isinstance(msg, ResultMessage):
            if msg.is_error:
                raise RuntimeError(f"Claude step failed: {msg.result or msg.errors}")
            text = msg.result or ""
            structured = msg.structured_output
            cost = msg.total_cost_usd or 0.0
    return text, structured, cost


def run_step(task: str, expect: list[Path], output_schema: dict | None = None) -> tuple[str, Any]:
    """Run one agent step and check that it wrote the files it was asked for."""
    text, structured, _ = asyncio.run(_run(task, _options(output_schema=output_schema)))
    missing = [str(p) for p in expect if not (p.exists() and p.stat().st_size > 0)]
    if missing:
        raise RuntimeError(f"Claude finished but did not write: {', '.join(missing)}")
    return text, structured


QC_SCHEMA = {
    "type": "object",
    "properties": {"keep": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["keep", "reason"],
}


def qc_clip(key: str, step: dict, frames: list[Path], words: str) -> tuple[bool, str]:
    task = (
        f"Quality-check generated shot {key} for Phase 5 step 5. Look at each frame with the Read tool:\n"
        + "\n".join(f"- {f}" for f in frames)
        + f"\n\nVoiceover line it sits under: {words!r}\nPrompt it was made from:\n{step['params'].get('prompt', '')}\n\n"
        "Reject it if you see anything on the Phase 5 step 5 list or the Section 5.1 never-on-screen list. "
        "Reply with keep=true/false and a one-line reason."
    )
    from claude_agent_sdk import ClaudeAgentOptions  # noqa: F401  (import check)
    opts = _options(output_schema=QC_SCHEMA, max_turns=8)
    opts.allowed_tools = ["Read"]
    opts.mcp_servers = {}
    _, out, _ = asyncio.run(_run(task, opts))
    if not isinstance(out, dict):
        return False, "QC returned no verdict; held for a human look"
    return bool(out.get("keep")), str(out.get("reason", ""))[:300]
