import pytest

from app.engine.params import clamp_movetime, clamp_skill, resolve_move_params
from tests.conftest import make_settings


def test_clamp_skill_bounds():
    s = make_settings()
    assert clamp_skill(-5, s) == 0
    assert clamp_skill(50, s) == 20
    assert clamp_skill(9, s) == 9
    assert clamp_skill(None, s) is None


def test_clamp_movetime_bounds_and_default():
    s = make_settings(min_movetime_ms=50, max_movetime_ms=2000, default_movetime_ms=600)
    assert clamp_movetime(None, s) == 600
    assert clamp_movetime(1, s) == 50
    assert clamp_movetime(999999, s) == 2000
    assert clamp_movetime(600, s) == 600


def test_difficulty_preset_resolution():
    s = make_settings()
    # medium preset = (skill 9, movetime 600)
    skill, mt = resolve_move_params(
        skill_level=None, movetime_ms=None, difficulty="medium", settings=s
    )
    assert (skill, mt) == (9, 600)


def test_explicit_params_override_preset():
    s = make_settings()
    skill, mt = resolve_move_params(
        skill_level=20, movetime_ms=1500, difficulty="easy", settings=s
    )
    assert (skill, mt) == (20, 1500)


def test_unknown_difficulty_raises():
    s = make_settings()
    with pytest.raises(ValueError):
        resolve_move_params(
            skill_level=None, movetime_ms=None, difficulty="impossible", settings=s
        )


def test_no_params_uses_default_movetime():
    s = make_settings(default_movetime_ms=600)
    skill, mt = resolve_move_params(
        skill_level=None, movetime_ms=None, difficulty=None, settings=s
    )
    assert skill is None and mt == 600
