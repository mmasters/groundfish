"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MoveRequest(BaseModel):
    """A best-move request. Supply either explicit params, a difficulty preset, or both
    (explicit ``skill_level`` / ``movetime_ms`` win over the preset)."""

    fen: str = Field(..., description="Board position in Forsyth-Edwards Notation.")
    skill_level: int | None = Field(
        default=None, ge=0, le=20, description="UCI Skill Level (0-20)."
    )
    movetime_ms: int | None = Field(
        default=None, ge=1, description="Search time budget in milliseconds (will be clamped)."
    )
    difficulty: str | None = Field(
        default=None, description="Preset: easy | medium | hard."
    )


class MoveResponse(BaseModel):
    bestmove: str | None = Field(
        ..., description="Best move in UCI notation, or null for a terminal position."
    )


class UCIRequest(BaseModel):
    commands: list[str] = Field(
        ..., description="Ordered UCI commands to run on a freshly-reset engine."
    )


class UCIResponse(BaseModel):
    lines: list[str] = Field(..., description="Raw engine output lines.")
    bestmove: str | None = Field(default=None)
    ponder: str | None = Field(default=None)


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    engines_alive: int
    pool_size: int


class EngineInfoResponse(BaseModel):
    name: str
    authors: str
    pool_size: int
    default_movetime_ms: int
    max_movetime_ms: int
    difficulty_presets: dict[str, list[int]]
