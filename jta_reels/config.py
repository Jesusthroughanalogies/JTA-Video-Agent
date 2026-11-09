"""Settings that come from the environment (.env on the server). Secrets never live in code."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO / "reels_probe"      # Week 1 proof snapshots (git-ignored)


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: Path = REPO / ".env") -> None:
    """KEY=VALUE lines from .env into the environment, without overriding what's already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    database_url: str = ""
    ig_user_id: str = ""
    ig_access_token: str = ""
    # Instagram API with Facebook Login (Page-linked account, system user token).
    ig_graph_host: str = "graph.facebook.com"
    ig_graph_version: str = "v24.0"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    signed_url_seconds: int = 3600    # how long Meta has to fetch the MP4
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    ENV = {
        "database_url": "JTA_DATABASE_URL",
        "ig_user_id": "IG_USER_ID",
        "ig_access_token": "IG_ACCESS_TOKEN",
        "ig_graph_host": "IG_GRAPH_HOST",
        "ig_graph_version": "IG_GRAPH_VERSION",
        "r2_account_id": "R2_ACCOUNT_ID",
        "r2_access_key_id": "R2_ACCESS_KEY_ID",
        "r2_secret_access_key": "R2_SECRET_ACCESS_KEY",
        "r2_bucket": "R2_BUCKET",
        "signed_url_seconds": "R2_SIGNED_URL_SECONDS",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id": "TELEGRAM_CHAT_ID",
    }

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        kw = {}
        for f in fields(cls):
            raw = os.environ.get(cls.ENV[f.name])
            if raw:
                kw[f.name] = int(raw) if f.type in (int, "int") else raw
        return cls(**kw)

    def require(self, *names: str) -> "Config":
        missing = [self.ENV[n] for n in names if not getattr(self, n)]
        if missing:
            raise ConfigError("missing in .env: " + ", ".join(missing))
        return self

    @property
    def has_r2(self) -> bool:
        return all((self.r2_account_id, self.r2_access_key_id, self.r2_secret_access_key, self.r2_bucket))

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)
