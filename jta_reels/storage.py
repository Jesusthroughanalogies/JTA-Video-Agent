"""Cloudflare R2 (S3-compatible) with presigned links, signed here with AWS Signature V4.

No SDK: Instagram only needs a short-lived GET link to the MP4, and the Creator a PUT link to
upload one. Signing is ~40 lines of stdlib and is tested against AWS's published example.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import urllib.parse
import urllib.request
from pathlib import Path


def _q(s: str, safe: str = "-_.~") -> str:
    return urllib.parse.quote(s, safe=safe)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def presign_url(method: str, host: str, path: str, *, region: str, access_key: str, secret_key: str,
                expires: int = 3600, now: dt.datetime | None = None, service: str = "s3") -> str:
    """A SigV4 query-string presigned URL (UNSIGNED-PAYLOAD, only the host header signed)."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    amz_date, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    canonical_uri = _q(path, safe="-_.~/")
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    cqs = "&".join(f"{_q(k)}={_q(v)}" for k, v in sorted(query.items()))
    canonical_request = "\n".join([method, canonical_uri, cqs, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"])
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                                hashlib.sha256(canonical_request.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), datestamp), region), service), "aws4_request")
    sig = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{canonical_uri}?{cqs}&X-Amz-Signature={sig}"


class R2:
    def __init__(self, account_id: str, access_key: str, secret_key: str, bucket: str, *, expires: int = 3600):
        self.host = f"{account_id}.r2.cloudflarestorage.com"
        self.access_key, self.secret_key, self.bucket, self.expires = access_key, secret_key, bucket, expires

    @classmethod
    def from_config(cls, cfg) -> "R2":
        cfg.require("r2_account_id", "r2_access_key_id", "r2_secret_access_key", "r2_bucket")
        return cls(cfg.r2_account_id, cfg.r2_access_key_id, cfg.r2_secret_access_key, cfg.r2_bucket,
                   expires=cfg.signed_url_seconds)

    def _url(self, method: str, key: str, expires: int | None = None) -> str:
        return presign_url(method, self.host, f"/{self.bucket}/{key.lstrip('/')}", region="auto",
                           access_key=self.access_key, secret_key=self.secret_key,
                           expires=expires or self.expires)

    def get_url(self, key: str, expires: int | None = None) -> str:
        """The short-lived link Instagram downloads the MP4 from."""
        return self._url("GET", key, expires)

    def upload(self, local: Path, key: str, content_type: str = "video/mp4") -> str:
        data = Path(local).read_bytes()
        req = urllib.request.Request(self._url("PUT", key, 900), data=data, method="PUT",
                                     headers={"Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=300) as r:
            if r.status not in (200, 201):
                raise RuntimeError(f"R2 upload of {key} returned HTTP {r.status}")
        return key
