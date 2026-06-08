"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from app.engine.manager import EnginePool


def get_pool(request: Request) -> EnginePool:
    return request.app.state.pool
