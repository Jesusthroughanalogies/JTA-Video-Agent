"""Higgsfield access for the generation executor.

Only this module talks to Higgsfield, and only the executor (generate.py)
uses it. Claude never gets Higgsfield generation tools directly (llm.py blocks
them), so every credit goes through the ledger.

Failure classes, which decide what is safe after an error:
  NotSent        the request never left (no connection). Safe to retry.
  Rejected       Higgsfield answered "no" (e.g. not enough credits). No job, no charge.
  OutcomeUnknown the request may have reached Higgsfield (timeout, dropped
                 connection, crash). Never resubmit blindly: reconcile against
                 history first (generate.reconcile).

Response shapes below were taken from real Higgsfield MCP responses on
2 Nov 2026 (get_cost, jobs_wait, show_generations). The submit response
(generate_video / generate_image without get_cost) was not observed, because
it costs credits, so parse_submit() is deliberately tolerant and anything it
cannot read becomes OutcomeUnknown, which reconciliation resolves from history.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
TERMINAL_OK = {"completed", "succeeded", "success", "done"}
TERMINAL_FAIL = {"failed", "error", "canceled", "cancelled", "nsfw", "rejected", "expired"}


class NotSent(Exception):
    pass


class Rejected(Exception):
    pass


class OutcomeUnknown(Exception):
    pass


class NetworkDown(Exception):
    """A read-only call (wait, history, balance) failed on the network. Retry later."""


@dataclass
class SubmitResult:
    job_ids: list[str]
    preset_id: Optional[str] = None      # Higgsfield suggested a preset instead of running
    needs_human: Optional[str] = None    # e.g. a recovery_tool we won't call on our own
    raw: Any = None


@dataclass
class JobStatus:
    job_id: str
    state: str                  # "active" | "completed" | "failed"
    raw_status: str = ""
    result_url: Optional[str] = None


@dataclass
class HistoryItem:
    job_id: str
    status: str
    prompt: str
    created_at: float
    model: str = ""
    extra: dict = field(default_factory=dict)


class Backend(Protocol):
    def get_cost(self, tool: str, params: dict) -> float: ...
    def submit(self, tool: str, params: dict) -> SubmitResult: ...
    def wait(self, job_ids: list[str], timeout: int = 15) -> dict[str, JobStatus]: ...
    def history(self, pages: int = 3, page_size: int = 50) -> list[HistoryItem]: ...
    def balance(self) -> Optional[float]: ...
    def download(self, url: str, dest: Path) -> None: ...


# ---------------------------------------------------------------- parsing
def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def parse_cost(data: dict) -> float:
    # Observed: {"cost": {"credits": 8.75, "credits_exact": 8.75}}
    c = data.get("cost", data)
    for k in ("credits_exact", "credits"):
        if isinstance(c, dict) and isinstance(c.get(k), (int, float)):
            return float(c[k])
    raise ValueError(f"no cost in response: {str(data)[:200]}")


def parse_submit(data: Any) -> SubmitResult:
    ids: list[str] = []
    preset: Optional[str] = None
    human: Optional[str] = None
    for d in _walk(data):
        for k in ("job_id", "jobId"):
            v = d.get(k)
            if isinstance(v, str) and UUID_RE.match(v) and v not in ids:
                ids.append(v)
        if "jobs" in d and isinstance(d["jobs"], list):
            for j in d["jobs"]:
                if isinstance(j, dict):
                    v = j.get("id") or j.get("job_id")
                    if isinstance(v, str) and UUID_RE.match(v) and v not in ids:
                        ids.append(v)
        for k, v in d.items():
            if "preset" in k.lower() and k != "declined_preset_id":
                if isinstance(v, dict) and isinstance(v.get("id"), str):
                    preset = preset or v["id"]
                elif k.lower() in ("recommended_preset_id", "suggested_preset_id", "preset_id") and isinstance(v, str):
                    preset = preset or v
        if d.get("recovery_tool"):
            human = f"Higgsfield asked to run recovery tool {d['recovery_tool']!r}"
        if d.get("unlim_choice"):
            human = "Higgsfield asked whether to use unlimited generations"
    if ids:
        preset = None  # a job was created; any suggestion is moot
    return SubmitResult(job_ids=ids, preset_id=preset, needs_human=None if ids else human, raw=data)


def parse_wait(data: dict) -> dict[str, JobStatus]:
    # Observed: {"jobs":[{"index":0,"job_id":..,"status":"completed","result_url":..}], "all_terminal": true}
    out: dict[str, JobStatus] = {}
    for j in data.get("jobs", []):
        s = str(j.get("status", "")).lower()
        state = "completed" if s in TERMINAL_OK else "failed" if s in TERMINAL_FAIL else "active"
        if j.get("error") and state == "active" and not s:
            state = "failed"
        out[j["job_id"]] = JobStatus(j["job_id"], state, s, j.get("result_url"))
    return out


def parse_history(data: dict) -> tuple[list[HistoryItem], Any]:
    # Observed: {"items":[{"id","type","status","model","params":{"prompt":..},"createdAt":..}], "next_cursor":..}
    items = []
    for it in data.get("items", []):
        items.append(HistoryItem(
            job_id=it["id"], status=str(it.get("status", "")).lower(),
            prompt=(it.get("params") or {}).get("prompt", ""),
            created_at=float(it.get("createdAt") or 0), model=it.get("model", ""),
        ))
    return items, data.get("next_cursor")


# ---------------------------------------------------------------- live backend
class McpBackend:
    """Calls the Higgsfield MCP server over streamable HTTP.

    Configure with HIGGSFIELD_MCP_URL and HIGGSFIELD_MCP_TOKEN (sent as a
    Bearer token). One short session per call, so a dropped connection never
    leaves a half-dead session behind.
    """

    def __init__(self, url: Optional[str] = None, token: Optional[str] = None, call_timeout: float = 120):
        self.url = url or os.environ.get("HIGGSFIELD_MCP_URL", "")
        self.token = token or os.environ.get("HIGGSFIELD_MCP_TOKEN", "")
        self.call_timeout = call_timeout

    async def _call_async(self, name: str, args: dict) -> Any:
        from mcp import ClientSession
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        async with streamable_http_client(self.url, http_client=create_mcp_http_client(headers=headers)) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool(name, args, read_timeout_seconds=self.call_timeout)
        data: Any = getattr(res, "structured_content", None)
        if data is None:
            text = "".join(getattr(c, "text", "") for c in getattr(res, "content", []) or [])
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                data = {"text": text}
        if getattr(res, "is_error", False):
            raise Rejected(str(data)[:500])
        return data

    def _call(self, name: str, args: dict, *, mutating: bool) -> Any:
        if not self.url:
            raise RuntimeError("HIGGSFIELD_MCP_URL is not set (see .env.example)")
        try:
            return asyncio.run(self._call_async(name, args))
        except (Rejected, KeyboardInterrupt):
            raise
        except BaseException as e:  # noqa: BLE001 - classify every transport failure
            names = {type(x).__name__ for x in _exc_chain(e)}
            if names & {"ConnectError", "ConnectTimeout", "PoolTimeout", "ProxyError"} \
                    and not names & {"ReadTimeout", "ReadError", "RemoteProtocolError", "WriteError"}:
                raise (NotSent if mutating else NetworkDown)(f"{name}: no connection ({e!r})") from e
            raise (OutcomeUnknown if mutating else NetworkDown)(f"{name}: {e!r}") from e

    def get_cost(self, tool: str, params: dict) -> float:
        data = self._call(tool, {"params": {**params, "get_cost": True}}, mutating=False)
        return parse_cost(data)

    def submit(self, tool: str, params: dict) -> SubmitResult:
        # use_unlim=False: always pay with credits so the ledger is exact and
        # Higgsfield never stops to ask about free-trial allowances.
        data = self._call(tool, {"params": {**params, "use_unlim": False}}, mutating=True)
        return parse_submit(data)

    def wait(self, job_ids: list[str], timeout: int = 15) -> dict[str, JobStatus]:
        out: dict[str, JobStatus] = {}
        for i in range(0, len(job_ids), 12):  # jobs_wait takes at most 12
            group = [{"index": n, "job_id": j} for n, j in enumerate(job_ids[i:i + 12])]
            out.update(parse_wait(self._call("jobs_wait", {"jobs": group, "timeout_seconds": min(timeout, 15)},
                                             mutating=False)))
        return out

    def history(self, pages: int = 3, page_size: int = 50) -> list[HistoryItem]:
        items: list[HistoryItem] = []
        cursor = None
        for _ in range(pages):
            args: dict = {"only_completed": False, "size": page_size}
            if cursor is not None:
                args["cursor"] = cursor
            page, cursor = parse_history(self._call("show_generations", args, mutating=False))
            items += page
            if not cursor:
                break
        return items

    def balance(self) -> Optional[float]:
        data = self._call("balance", {}, mutating=False)
        v = data.get("credits") if isinstance(data, dict) else None
        return float(v) if isinstance(v, (int, float)) else None

    def download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
        except OSError as e:
            raise NetworkDown(f"download failed: {e!r}") from e
        os.replace(tmp, dest)


def _exc_chain(e: BaseException):
    seen = set()
    stack = [e]
    while stack:
        x = stack.pop()
        if id(x) in seen:
            continue
        seen.add(id(x))
        yield x
        if isinstance(x, BaseExceptionGroup):
            stack.extend(x.exceptions)
        for nxt in (x.__cause__, x.__context__):
            if nxt is not None:
                stack.append(nxt)
