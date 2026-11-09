"""Test doubles for the Trial Reel Agent: a fake Graph API server, fake storage, a test database."""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid

import pytest

from jta_reels.instagram import GraphError, Instagram

UTC = dt.timezone.utc
IG_USER = "17841400000000000"


class FakeGraph:
    """Speaks just enough of the Graph API for the publisher and insights jobs.

    Failure switches:
      container_polls       status polls before a new container is FINISHED
      container_error       new containers end in ERROR
      drop_after_publish    media_publish succeeds on the server, then the connection drops
      drop_before_publish   the connection drops before media_publish reaches the server
      unsupported_metrics   metrics the insights endpoint rejects with error 100
    """

    def __init__(self):
        self.containers: dict[str, dict] = {}
        self.media: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self.container_polls = 1
        self.container_error = False
        self.drop_after_publish = False
        self.drop_before_publish = False
        self.unsupported_metrics = {"follows"}
        self.shared_to_feed: dict[str, bool] = {}
        self.clock = lambda: dt.datetime.now(UTC)

    # Transport protocol
    def request(self, method: str, url: str, params: dict) -> tuple[int, dict]:
        path = url.split("/v24.0/", 1)[1]
        self.calls.append((method, path, dict(params)))
        if method == "POST" and path == f"{IG_USER}/media":
            cid = f"c{len(self.containers) + 1}"
            self.containers[cid] = {"params": params, "polls": 0, "published": None}
            return 200, {"id": cid}
        if method == "POST" and path == f"{IG_USER}/media_publish":
            if self.drop_before_publish:
                self.drop_before_publish = False
                raise GraphError("network: connection reset", transient=True)
            c = self.containers[params["creation_id"]]
            if c["published"]:
                return 400, {"error": {"code": 9007, "message": "already published"}}
            mid = f"m{len(self.media) + 1}"
            c["published"] = mid
            self.media[mid] = {"id": mid, "caption": c["params"]["caption"], "media_type": "VIDEO",
                               "media_product_type": "REELS", "permalink": f"https://instagram.com/reel/{mid}",
                               "timestamp": self.clock().strftime("%Y-%m-%dT%H:%M:%S+0000")}
            if self.drop_after_publish:
                self.drop_after_publish = False
                raise GraphError("network: connection reset", transient=True)
            return 200, {"id": mid}
        if method == "GET" and path == f"{IG_USER}/media":
            return 200, {"data": sorted(self.media.values(), key=lambda m: m["id"], reverse=True)}
        if method == "GET" and path.endswith("/insights"):
            mid = path.split("/")[0]
            names = params["metric"].split(",")
            bad = [n for n in names if n in self.unsupported_metrics]
            if bad:
                return 400, {"error": {"code": 100, "message": f"(#100) metric[0] must be one of ... not {bad[0]}"}}
            data = []
            for n in names:
                v = {"ig_reels_avg_watch_time": 12500, "ig_reels_video_view_total_time": 9_000_000}.get(n, 100)
                item = {"name": n, "period": "lifetime"}
                if n == "views":
                    item["total_value"] = {"value": 4200}
                else:
                    item["values"] = [{"value": v}]
                data.append(item)
            return 200, {"data": data}
        if method == "GET" and path in self.containers:
            c = self.containers[path]
            if c["published"]:
                return 200, {"status_code": "PUBLISHED", "id": path}
            if self.container_error:
                return 200, {"status_code": "ERROR", "status": "Error: 2207026 unsupported video"}
            c["polls"] += 1
            return 200, {"status_code": "FINISHED" if c["polls"] > self.container_polls else "IN_PROGRESS"}
        if method == "GET" and path in self.media:
            m = self.media[path]
            fields = params["fields"].split(",")
            if fields == ["is_shared_to_feed"]:
                return 200, {"id": path, "is_shared_to_feed": self.shared_to_feed.get(path, False)}
            return 200, {k: m[k] for k in fields if k in m}
        return 404, {"error": {"code": 803, "message": f"unknown path {method} {path}"}}

    def published_count(self) -> int:
        return sum(1 for c in self.containers.values() if c["published"])


class FakeStorage:
    def get_url(self, key: str, expires: int | None = None) -> str:
        return f"https://r2.test/{key}?sig=x"


def make_ig(graph: FakeGraph) -> Instagram:
    return Instagram(IG_USER, "token", transport=graph, sleep=lambda s: None)


@pytest.fixture
def db():
    """A fresh schema per test in the database named by JTA_TEST_DATABASE_URL."""
    url = os.environ.get("JTA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set JTA_TEST_DATABASE_URL to run the database tests")
    pytest.importorskip("psycopg")
    from jta_reels.db import DB
    schema = f"t_{uuid.uuid4().hex[:10]}"
    admin = DB(url)
    admin.q(f"create schema {schema}")
    d = DB(url, search_path=schema)
    d.migrate()
    yield d
    d.close()
    admin.q(f"drop schema {schema} cascade")
    admin.close()


def jdump(x) -> str:
    return json.dumps(x, default=str)
