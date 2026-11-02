"""Run: python -m pytest -q  (or python tests/test_rules.py)"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jta_visuals import rules
from jta_visuals.prompts import Shot, build_frame_prompt, build_video_prompt, validate


def ai(**kw):
    base = dict(id="T", tag="AI", camera="Slow push-in.", scene="A shepherd on a hill.", light="Dawn.")
    base.update(kw)
    return Shot(**base)


def test_clean_shot_passes():
    assert validate(ai()) == []


def test_modern_words_rejected():
    for scene in ["A man reading a Bible by a window.", "A coffee mug on a table.",
                  "A vintage control panel glows.", "A man in jeans walks.", "City skyline at night."]:
        assert validate(ai(scene=scene)), scene


def test_word_boundaries():
    # 'watching' must not trip 'watch'; 'watchtower' must not trip 'tower'
    assert validate(ai(scene="A woman watching the sea from a stone watchtower.")) == []


def test_jesus_needs_token_and_two_steps():
    assert validate(ai(jesus=True)), "jesus=True without {JESUS} must fail"
    s = ai(jesus=True, scene="{JESUS} walks along the shore.")
    assert validate(s) == []
    assert rules.JESUS_TOKEN in build_video_prompt(s)
    assert rules.JESUS_TOKEN in build_frame_prompt(s)
    assert "never visible" in build_video_prompt(s)


def test_every_prompt_ends_ancient_or_nature():
    assert build_video_prompt(ai()).endswith(rules.ANCIENT_ENDING)
    assert build_video_prompt(ai(nature=True)).endswith(rules.NATURE_ENDING)


def test_other_people_dress_rule():
    assert rules.OTHER_PEOPLE_DRESS in build_video_prompt(ai(people=True))


def test_episode_1_passes_and_fits_cap():
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "jta_visuals.plan", "episodes/ep001/shots.py"],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_one_version_per_shot():
    # Matt, 2 Nov 2026: never generate alternatives to choose between
    assert ai(hero=True).variants == 1 and ai().variants == 1
