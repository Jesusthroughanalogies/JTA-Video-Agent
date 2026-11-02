"""Per-episode credit ledger with a hard cap.

episodes/<id>/ledger.jsonl is append-only. Entry kinds:
  reserve    written BEFORE a submit call, with the preflight cost
  submitted  the job id came back: the reserve becomes spent
  void       we know for sure no job was created: the reserve is released
  orphan     a job found in Higgsfield history that we did not track (counted as spent)
  cap_raise  a human approved going past the cap by N credits
  balance    a Higgsfield balance snapshot, for a cross-check

A reserve with no matching submitted/void counts as spent. That is the safe
side: after a crash mid-submit we assume the credits went until we prove they
didn't. The cap check runs before every submit and uses the larger of the
ledger total and the drop in the real Higgsfield balance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import store
from .state import now


class CapReached(Exception):
    def __init__(self, message: str, needed: float):
        super().__init__(message)
        self.needed = needed


class Ledger:
    def __init__(self, path: Path, cap: float):
        self.path = path
        self.base_cap = cap

    def _entries(self) -> list[dict]:
        return list(store.read_jsonl(self.path))

    def _add(self, kind: str, **fields) -> None:
        store.append_jsonl(self.path, {"t": now(), "kind": kind, **fields})

    # ---- writes ---------------------------------------------------------
    def reserve(self, key: str, attempt: int, credits: float) -> None:
        self._add("reserve", key=key, attempt=attempt, credits=credits)

    def submitted(self, key: str, attempt: int, job_id: str, credits: float) -> None:
        self._add("submitted", key=key, attempt=attempt, job_id=job_id, credits=credits)

    def void(self, key: str, attempt: int, reason: str) -> None:
        self._add("void", key=key, attempt=attempt, reason=reason)

    def orphan(self, job_id: str, credits: float, note: str) -> None:
        self._add("orphan", job_id=job_id, credits=credits, note=note)

    def raise_cap(self, extra: float, by: str) -> None:
        self._add("cap_raise", extra=extra, by=by)

    def balance(self, credits: float) -> None:
        self._add("balance", credits=credits)

    # ---- totals ----------------------------------------------------------
    def totals(self) -> dict:
        reserves: dict[tuple, float] = {}
        closed: set[tuple] = set()
        spent = 0.0
        extra = 0.0
        balances: list[float] = []
        for e in self._entries():
            k = e["kind"]
            if k == "reserve":
                reserves[(e["key"], e["attempt"])] = e["credits"]
            elif k == "submitted":
                closed.add((e["key"], e["attempt"]))
                spent += e["credits"]
            elif k == "void":
                closed.add((e["key"], e["attempt"]))
            elif k == "orphan":
                spent += e["credits"]
            elif k == "cap_raise":
                extra += e["extra"]
            elif k == "balance":
                balances.append(e["credits"])
        open_reserved = sum(c for ka, c in reserves.items() if ka not in closed)
        balance_drop: Optional[float] = None
        if len(balances) >= 2:
            balance_drop = round(balances[0] - balances[-1], 2)
        committed = round(spent + open_reserved, 2)
        return {
            "spent": round(spent, 2),
            "open_reserved": round(open_reserved, 2),
            "committed": committed,
            "balance_drop": balance_drop,
            "effective": max(committed, balance_drop or 0.0),
            "cap": self.base_cap + extra,
            "base_cap": self.base_cap,
            "approved_extra": extra,
        }

    def check(self, cost: float, what: str) -> None:
        t = self.totals()
        after = t["effective"] + cost
        if after > t["cap"] + 1e-9:
            src = "ledger"
            if t["balance_drop"] is not None and t["balance_drop"] > t["committed"]:
                src = "your Higgsfield balance (it dropped more than this episode's ledger)"
            raise CapReached(
                f"{what} costs {cost:g} credits. This episode has used {t['effective']:g} "
                f"of its {t['cap']:g}-credit cap (per {src}), so it would reach {after:g}.",
                needed=round(after - t["cap"], 2),
            )
