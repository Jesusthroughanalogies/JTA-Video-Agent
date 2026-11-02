"""Every [ANIM] and [TEXT] shot in Ep 1 has an animation scene, and scenes render."""
from pathlib import Path

from jta_anim.scenes_ep001 import REG, render_shot
from jta_visuals.plan import load_shots

REPO = Path(__file__).resolve().parents[1]


def test_every_anim_and_text_shot_has_a_scene():
    _, shots = load_shots(REPO / "episodes/ep001/shots.py")
    need = {s.id for s in shots if s.tag in ("ANIM", "TEXT")}
    assert need - set(REG) == set()
    assert set(REG) - need == set()


def test_scenes_render_with_word_timing(tmp_path):
    for sid in ("P1-01", "P2-04", "P4-16", "P1-12T"):
        out = render_shot(sid, 4.0, tmp_path / f"{sid}.png", line="Turn one dial slightly, and there are no stars.",
                          still_at=3.0)
        assert out.stat().st_size > 10_000


def test_no_navy_left_in_the_style():
    for p in (REPO / "jta_agent").glob("*.py"):
        assert "navy and gold" not in p.read_text(), p
