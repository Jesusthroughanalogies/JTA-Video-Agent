# JTA visuals: locked rules as code

Drop `jta_visuals/` into the agent repo and add `episodes/ep001/`.

- `jta_visuals/rules.py`: Jesus element id, Kling settings, credit costs, 1,200 cap, ancient-only wording, banned words, grade filter.
- `jta_visuals/prompts.py`: `Shot` model, `build_video_prompt`, `build_frame_prompt`, `validate`.
- `jta_visuals/plan.py`: `python -m jta_visuals.plan episodes/ep001/shots.py` validates every shot, estimates credits and writes `generation_plan.json` (exact Higgsfield tool params, in order; `{{job:KEY}}` = the job id of an earlier step).
- `episodes/ep001/shots.py`: Ep 1, row by row from the script doc.
- `tests/test_rules.py`: `python tests/test_rules.py`.

Grade in the edit: `ffmpeg -i in.mp4 -vf "<GRADE_FILTER>" out.mp4`.
