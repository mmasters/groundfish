"""Clamping of search parameters and difficulty-preset resolution.

These are the primary per-request CPU guards: movetime and skill are always clamped to
configured bounds before reaching the engine.
"""

from __future__ import annotations

from app.config import Settings

SKILL_MIN = 0
SKILL_MAX = 20


def clamp_skill(skill: int | None, settings: Settings) -> int | None:
    """Clamp a UCI ``Skill Level`` to [0, 20]. ``None`` means 'leave at default'."""
    if skill is None:
        return None
    return max(SKILL_MIN, min(SKILL_MAX, int(skill)))


def clamp_movetime(movetime_ms: int | None, settings: Settings) -> int:
    """Clamp movetime to [min, max]; fall back to the configured default when unset."""
    if movetime_ms is None:
        movetime_ms = settings.default_movetime_ms
    return max(settings.min_movetime_ms, min(settings.max_movetime_ms, int(movetime_ms)))


def resolve_move_params(
    *,
    skill_level: int | None,
    movetime_ms: int | None,
    difficulty: str | None,
    settings: Settings,
) -> tuple[int | None, int]:
    """Resolve (skill, movetime) for a /move request.

    A ``difficulty`` preset supplies defaults; explicit ``skill_level`` / ``movetime_ms``
    override the preset. Returns clamped ``(skill, movetime_ms)``.
    """
    preset_skill: int | None = None
    preset_movetime: int | None = None
    if difficulty is not None:
        preset = settings.difficulty_presets.get(difficulty.lower())
        if preset is None:
            valid = ", ".join(sorted(settings.difficulty_presets))
            raise ValueError(f"Unknown difficulty {difficulty!r}; expected one of: {valid}")
        preset_skill, preset_movetime = preset

    skill = skill_level if skill_level is not None else preset_skill
    movetime = movetime_ms if movetime_ms is not None else preset_movetime

    return clamp_skill(skill, settings), clamp_movetime(movetime, settings)
