"""Validate an episode shot list, estimate credits and write the generation plan.

Usage:  python -m jta_visuals.plan episodes/ep001/shots.py
Writes: episodes/<ep>/generation_plan.json  (exact Higgsfield tool parameters, in order)
Exit code 1 if any shot fails validation or the estimate is over the credit cap.
"""
from __future__ import annotations

import collections
import importlib.util
import json
import math
import sys
from pathlib import Path

from . import rules
from .prompts import Shot, build_frame_prompt, build_video_prompt, validate


def load_shots(path: Path) -> tuple[str, list[Shot]]:
    spec = importlib.util.spec_from_file_location("episode_shots", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.EPISODE_ID, mod.SHOTS


def plan(shots: list[Shot]) -> tuple[list[dict], float]:
    steps: list[dict] = []
    credits = 0.0
    for s in shots:
        if s.tag != "AI" or s.reuse:
            continue
        for v in range(1, s.variants + 1):
            key = f"{s.id}-v{v}"
            medias = []
            if s.jesus:
                if s.start_frame:
                    frame_ref = s.start_frame
                else:
                    frame_ref = f"{{{{job:{key}-frame}}}}"
                    steps.append({
                        "key": f"{key}-frame",
                        "tool": "generate_image",
                        "params": {"model": rules.FRAME_MODEL, **rules.FRAME_PARAMS,
                                   "prompt": build_frame_prompt(s)},
                        "credits": rules.CREDITS_PER_FRAME,
                    })
                    credits += rules.CREDITS_PER_FRAME
                medias = [{"role": "start_image", "value": frame_ref}]
            params = {"model": rules.VIDEO_MODEL, **rules.VIDEO_PARAMS,
                      "prompt": build_video_prompt(s)}
            if medias:
                params["medias"] = medias
            steps.append({
                "key": key,
                "tool": "generate_video",
                "depends_on": [f"{key}-frame"] if s.jesus and not s.start_frame else [],
                "params": params,
                "credits": rules.CREDITS_PER_CLIP,
            })
            credits += rules.CREDITS_PER_CLIP
    return steps, credits


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    episode_id, shots = load_shots(path)

    errors = [e for s in shots for e in validate(s)]
    ids = [s.id for s in shots]
    dupes = [i for i, n in collections.Counter(ids).items() if n > 1]
    errors += [f"duplicate shot id {d}" for d in dupes]
    known = set(ids)
    errors += [f"{s.id}: background {s.background} not found"
               for s in shots if s.background and s.background not in known]

    steps, planned = plan(shots)
    with_redos = planned * (1 + rules.REDO_ALLOWANCE)

    tags = collections.Counter(s.tag for s in shots)
    ai = [s for s in shots if s.tag == "AI"]
    print(f"Episode {episode_id}: {len(shots)} shots  " +
          "  ".join(f"{t} {n}" for t, n in sorted(tags.items())))
    print(f"AI shots: {len(ai)} ({sum(1 for s in ai if s.reuse)} reused, "
          f"{sum(1 for s in ai if s.jesus)} Jesus, {sum(1 for s in ai if s.hero)} hero)")
    print(f"Generations: {sum(1 for x in steps if x['tool']=='generate_video')} clips, "
          f"{sum(1 for x in steps if x['tool']=='generate_image')} start frames")
    print(f"Credits planned: {planned:.1f}  with {int(rules.REDO_ALLOWANCE*100)}% redos: "
          f"{with_redos:.1f}  cap: {rules.EPISODE_CREDIT_CAP}")

    if with_redos > rules.EPISODE_CREDIT_CAP:
        errors.append(f"estimate {with_redos:.0f} is over the {rules.EPISODE_CREDIT_CAP} credit cap")

    out = path.parent / "generation_plan.json"
    out.write_text(json.dumps({
        "episode": episode_id,
        "credits_planned": planned,
        "credits_with_redos": math.ceil(with_redos),
        "credit_cap": rules.EPISODE_CREDIT_CAP,
        "grade_filter": rules.GRADE_FILTER,
        "reused": {s.id: s.reuse for s in shots if s.reuse},
        "steps": steps,
    }, indent=2))
    print(f"Wrote {out}")

    if errors:
        print("\nERRORS:")
        for e in errors:
            print("  -", e)
        return 1
    print("All shots pass the visual rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
