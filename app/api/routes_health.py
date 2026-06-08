"""Health and engine-info routes (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_pool
from app.api.schemas import EngineInfoResponse, HealthResponse, ReadyResponse
from app.config import get_settings
from app.engine.manager import EnginePool

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
async def readyz(response: Response, pool: EnginePool = Depends(get_pool)) -> ReadyResponse:
    alive = pool.engines_alive
    ready = alive > 0
    response.status_code = 200 if ready else 503
    return ReadyResponse(
        status="ready" if ready else "starting",
        engines_alive=alive,
        pool_size=pool.pool_size,
    )


@router.get("/engine/info", response_model=EngineInfoResponse)
async def engine_info(pool: EnginePool = Depends(get_pool)) -> EngineInfoResponse:
    settings = get_settings()
    worker = pool.sample_worker()
    presets = {k: [v[0], v[1]] for k, v in settings.difficulty_presets.items()}
    return EngineInfoResponse(
        name=worker.name if worker else "unknown",
        authors=worker.author if worker else "",
        pool_size=pool.pool_size,
        default_movetime_ms=settings.default_movetime_ms,
        max_movetime_ms=settings.max_movetime_ms,
        difficulty_presets=presets,
    )
