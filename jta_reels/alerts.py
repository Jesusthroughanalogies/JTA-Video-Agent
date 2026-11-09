"""Alerts to Matt. Telegram when configured (Week 4 adds pause/resume by message); stderr always."""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request


class Alerts:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token, self.chat_id = bot_token, chat_id
        self.sent: list[str] = []

    @classmethod
    def from_config(cls, cfg) -> "Alerts":
        return cls(cfg.telegram_bot_token, cfg.telegram_chat_id)

    def __call__(self, text: str) -> None:
        self.sent.append(text)
        print(f"ALERT: {text}", file=sys.stderr)
        if not (self.bot_token and self.chat_id):
            return
        data = urllib.parse.urlencode({"chat_id": self.chat_id, "text": f"JTA reels: {text}"}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{self.bot_token}/sendMessage", data=data, timeout=20)
        except Exception as e:  # an alert failing must never break the job that raised it
            print(f"(telegram failed: {e})", file=sys.stderr)


def jsonable(x) -> str:
    return json.dumps(x, default=str, indent=2)
