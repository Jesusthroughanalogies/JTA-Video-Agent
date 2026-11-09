"""Instagram Graph API: trial reels, container status, media fields and insights.

Plain code, no agent. The rules that keep posting safe live here and in publisher.py:
- Only GET requests are retried. A POST is never repeated automatically: a repeated
  media_publish could double-post. An unknown POST outcome is settled on the next run
  by reading the container's status instead.
- Insight metrics are asked for together, and one at a time if Meta rejects the set,
  so one unsupported metric (follows on reels, for example) never hides the others.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

GRADUATION_STRATEGIES = ("MANUAL", "SS_PERFORMANCE")

# Safe on every IG Media object. Extra fields are read one at a time (see media_field).
MEDIA_FIELDS = "id,media_type,media_product_type,permalink,timestamp,caption,like_count,comments_count"

# Fields Week 1 checks for a graduation signal. Each is read on its own; unknown ones just fail.
PROBE_FIELDS = ("id", "media_type", "media_product_type", "permalink", "shortcode", "timestamp",
                "caption", "like_count", "comments_count", "is_shared_to_feed", "is_comment_enabled",
                "thumbnail_url", "media_url", "owner", "username", "boost_eligibility_info")

# Every reel metric worth trying. Unsupported ones are found by the probe and remembered.
REEL_METRICS = ("views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
                "follows", "profile_visits", "profile_activity", "reels_skip_rate", "reposts")


class GraphError(Exception):
    def __init__(self, message: str, *, status: int = 0, code: int | None = None,
                 subcode: int | None = None, transient: bool = False, body: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.subcode, self.transient, self.body = status, code, subcode, transient, body or {}

    @classmethod
    def from_response(cls, status: int, body: dict) -> "GraphError":
        err = body.get("error", {}) if isinstance(body, dict) else {}
        code = err.get("code")
        # 1, 2, 4, 17, 32, 341, 613: temporary / rate limit. 5xx: Meta-side. is_transient: Meta says retry.
        transient = bool(err.get("is_transient")) or status >= 500 or code in (1, 2, 4, 17, 32, 341, 613)
        msg = err.get("error_user_msg") or err.get("message") or f"HTTP {status}"
        return cls(msg, status=status, code=code, subcode=err.get("error_subcode"), transient=transient, body=body)


class Transport(Protocol):
    def request(self, method: str, url: str, params: dict, headers: dict | None = None) -> tuple[int, dict]: ...


class UrllibTransport:
    """Real HTTP. GET sends params in the query, POST as a form body."""

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def request(self, method: str, url: str, params: dict, headers: dict | None = None) -> tuple[int, dict]:
        data = urllib.parse.urlencode(params).encode()
        h = dict(headers or {})
        if method == "GET":
            req = urllib.request.Request(f"{url}?{data.decode()}", method="GET", headers=h)
        else:
            h["Content-Type"] = "application/x-www-form-urlencoded"
            req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read() or b"{}")
            except ValueError:
                body = {}
            return e.code, body
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise GraphError(f"network: {e}", transient=True) from e


@dataclass
class ContainerStatus:
    code: str          # EXPIRED, ERROR, FINISHED, IN_PROGRESS, PUBLISHED
    detail: str = ""


class Instagram:
    def __init__(self, ig_user_id: str, token: str, *, host: str = "graph.facebook.com",
                 version: str = "v24.0", transport: Transport | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.ig_user_id, self.token = ig_user_id, token
        self.base = f"https://{host}/{version}"
        self.t = transport or UrllibTransport()
        self.sleep, self.clock = sleep, clock

    @classmethod
    def from_config(cls, cfg) -> "Instagram":
        cfg.require("ig_user_id", "ig_access_token")
        return cls(cfg.ig_user_id, cfg.ig_access_token, host=cfg.ig_graph_host, version=cfg.ig_graph_version)

    # ---- plumbing ---------------------------------------------------------
    def _call(self, method: str, path: str, params: dict | None = None, retries: int = 3) -> dict:
        p = {k: v for k, v in (params or {}).items() if v is not None}
        # The token goes in a header, never the URL, so it can't leak into logs or proxies' URL records.
        headers = {"Authorization": f"Bearer {self.token}"}
        attempts = retries + 1 if method == "GET" else 1
        for i in range(attempts):
            try:
                status, body = self.t.request(method, f"{self.base}/{path.lstrip('/')}", p, headers)
            except GraphError as e:
                if i + 1 < attempts:
                    self.sleep(2 ** i)
                    continue
                raise
            if 200 <= status < 300 and not (isinstance(body, dict) and "error" in body):
                return body
            err = GraphError.from_response(status, body)
            if err.transient and i + 1 < attempts:
                self.sleep(2 ** i)
                continue
            raise err
        raise AssertionError("unreachable")

    # ---- account ----------------------------------------------------------
    def account(self) -> dict:
        return self._call("GET", self.ig_user_id, {"fields": "id,username,name,followers_count,media_count"})

    def publishing_limit(self) -> dict:
        body = self._call("GET", f"{self.ig_user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
        return (body.get("data") or [{}])[0]

    # ---- publishing -------------------------------------------------------
    def create_trial_reel(self, video_url: str, caption: str, *, strategy: str = "MANUAL",
                          share_to_feed: bool | None = None, cover_url: str | None = None,
                          thumb_offset_ms: int | None = None) -> str:
        """Create a REELS container with trial_params. Returns the container id.

        Standard (non-resumable) upload: Meta fetches video_url itself. share_to_feed is left
        out unless asked for: a trial reel goes to non-followers only by definition.
        """
        if strategy not in GRADUATION_STRATEGIES:
            raise ValueError(f"graduation strategy must be one of {GRADUATION_STRATEGIES}")
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "trial_params": json.dumps({"graduation_strategy": strategy}),
            "cover_url": cover_url,
            "thumb_offset": thumb_offset_ms,
        }
        if share_to_feed is not None:
            params["share_to_feed"] = "true" if share_to_feed else "false"
        body = self._call("POST", f"{self.ig_user_id}/media", params)
        if not body.get("id"):
            raise GraphError(f"no container id in reply: {body}", body=body)
        return str(body["id"])

    def container_status(self, container_id: str) -> ContainerStatus:
        body = self._call("GET", container_id, {"fields": "status_code,status"})
        return ContainerStatus(str(body.get("status_code", "")), str(body.get("status", "")))

    def wait_until_ready(self, container_id: str, *, timeout: float = 900, poll: float = 10) -> ContainerStatus:
        """Poll until FINISHED (or PUBLISHED, which means an earlier run already published it)."""
        deadline = self.clock() + timeout
        while True:
            st = self.container_status(container_id)
            if st.code in ("FINISHED", "PUBLISHED"):
                return st
            if st.code in ("ERROR", "EXPIRED"):
                raise GraphError(f"container {container_id} {st.code}: {st.detail}")
            if self.clock() >= deadline:
                raise TimeoutError(f"container {container_id} still {st.code or 'unknown'} after {timeout:.0f}s")
            self.sleep(poll)

    def publish(self, container_id: str) -> str:
        """media_publish. Never retried here: the caller settles an unknown outcome from the container."""
        body = self._call("POST", f"{self.ig_user_id}/media_publish", {"creation_id": container_id})
        if not body.get("id"):
            raise GraphError(f"no media id in reply: {body}", body=body)
        return str(body["id"])

    # ---- reading ----------------------------------------------------------
    def media(self, media_id: str, fields: str = MEDIA_FIELDS) -> dict:
        return self._call("GET", media_id, {"fields": fields})

    def media_field(self, media_id: str, field: str) -> tuple[bool, object]:
        """One field on its own. (False, error message) if Meta doesn't know it for this media."""
        try:
            body = self.media(media_id, fields=field)
        except GraphError as e:
            if e.transient:
                raise
            return False, str(e)
        return True, body.get(field)

    def recent_media(self, limit: int = 25, fields: str = MEDIA_FIELDS) -> list[dict]:
        body = self._call("GET", f"{self.ig_user_id}/media", {"fields": fields, "limit": limit})
        return list(body.get("data") or [])

    def insights(self, media_id: str, metrics: Iterable[str]) -> tuple[dict, dict]:
        """(values, unsupported). Asks for all metrics at once; if Meta rejects the set, asks one by one."""
        metrics = list(metrics)
        if not metrics:
            return {}, {}
        try:
            return _parse_insights(self._call("GET", f"{media_id}/insights", {"metric": ",".join(metrics)})), {}
        except GraphError as e:
            if e.transient:
                raise
            if len(metrics) == 1:
                return {}, {metrics[0]: str(e)}
        values, unsupported = {}, {}
        for m in metrics:
            try:
                values.update(_parse_insights(self._call("GET", f"{media_id}/insights", {"metric": m})))
            except GraphError as e:
                if e.transient:
                    raise
                unsupported[m] = str(e)
        return values, unsupported


def _parse_insights(body: dict) -> dict:
    """Both reply shapes: values[0].value (lifetime metrics) and total_value.value (newer metrics)."""
    out = {}
    for item in body.get("data") or []:
        name = item.get("name")
        if not name:
            continue
        if isinstance(item.get("total_value"), dict) and "value" in item["total_value"]:
            out[name] = item["total_value"]["value"]
        elif item.get("values"):
            out[name] = item["values"][0].get("value")
    return out
