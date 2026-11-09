"""Week 1 proof. No database needed; just IG_USER_ID and IG_ACCESS_TOKEN (and R2 for --file).

  jta-reels probe account                         token works? account, publishing quota
  jta-reels probe post --file reel.mp4 --caption "..."   one real trial reel, end to end
  jta-reels probe read MEDIA_ID --label before    every field and metric, one at a time, saved
  (graduate it in the Instagram app)
  jta-reels probe read MEDIA_ID --label after
  jta-reels probe diff reels_probe/MEDIA_ID-before.json reels_probe/MEDIA_ID-after.json

The diff answers the two open questions: does Meta report follows per reel, and which
field (if any) changes when a trial reel graduates.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .config import PROBE_DIR
from .instagram import PROBE_FIELDS, REEL_METRICS, GraphError, Instagram


def _save(name: str, data: dict) -> Path:
    PROBE_DIR.mkdir(exist_ok=True)
    p = PROBE_DIR / name
    p.write_text(json.dumps(data, indent=2, default=str) + "\n")
    return p


def account(ig: Instagram) -> dict:
    out = {"account": ig.account()}
    try:
        out["publishing_limit"] = ig.publishing_limit()
    except GraphError as e:
        out["publishing_limit"] = f"unavailable: {e}"
    return out


def post(ig: Instagram, video_url: str, caption: str, *, strategy: str = "MANUAL",
         share_to_feed: bool | None = None, say=print) -> dict:
    say(f"creating trial reel container (graduation {strategy}) ...")
    cid = ig.create_trial_reel(video_url, caption, strategy=strategy, share_to_feed=share_to_feed)
    say(f"container {cid}; waiting for Instagram to process the video ...")
    st = ig.wait_until_ready(cid)
    say(f"container {st.code}; publishing ...")
    media_id = ig.publish(cid) if st.code != "PUBLISHED" else None
    rec = {"container_id": cid, "media_id": media_id, "strategy": strategy, "caption": caption,
           "posted_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if media_id:
        try:
            rec["media"] = ig.media(media_id)
        except GraphError as e:
            rec["media"] = f"unreadable: {e}"
    path = _save(f"post-{media_id or cid}.json", rec)
    say(f"posted media {media_id}. Saved {path}")
    return rec


def read(ig: Instagram, media_id: str, label: str = "snapshot") -> tuple[dict, Path]:
    fields, metrics = {}, {}
    for f in PROBE_FIELDS:
        ok, v = ig.media_field(media_id, f)
        fields[f] = {"ok": ok, "value": v}
    for m in REEL_METRICS:
        values, unsup = ig.insights(media_id, [m])
        metrics[m] = {"ok": m in values, "value": values.get(m)} if m not in unsup else {"ok": False, "error": unsup[m]}
    snap = {"media_id": media_id, "label": label, "read_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "fields": fields, "metrics": metrics}
    return snap, _save(f"{media_id}-{label}.json", snap)


def diff(a: dict, b: dict) -> list[str]:
    lines = []
    for section in ("fields", "metrics"):
        for k in sorted(set(a.get(section, {})) | set(b.get(section, {}))):
            x, y = a.get(section, {}).get(k), b.get(section, {}).get(k)
            if section == "metrics":     # counts always move; only report a metric appearing or vanishing
                if (x or {}).get("ok") != (y or {}).get("ok"):
                    lines.append(f"metric {k}: {'ok' if (x or {}).get('ok') else 'missing'} -> "
                                 f"{'ok' if (y or {}).get('ok') else 'missing'}")
            elif x != y and k not in ("like_count", "comments_count"):
                lines.append(f"field {k}: {json.dumps((x or {}).get('value'))} -> {json.dumps((y or {}).get('value'))}")
    return lines


def summary(snap: dict) -> str:
    f_ok = [k for k, v in snap["fields"].items() if v["ok"]]
    m_ok = [k for k, v in snap["metrics"].items() if v["ok"]]
    m_no = [k for k, v in snap["metrics"].items() if not v["ok"]]
    shared = snap["fields"].get("is_shared_to_feed", {})
    return "\n".join([
        f"fields readable:   {', '.join(f_ok)}",
        f"is_shared_to_feed: {shared.get('value') if shared.get('ok') else 'not readable'}",
        f"metrics reported:  {', '.join(m_ok) or 'none'}",
        f"metrics missing:   {', '.join(m_no) or 'none'}",
        f"follows per reel:  {'YES' if snap['metrics'].get('follows', {}).get('ok') else 'NO, score uses profile visits'}",
    ])
