"""POST /move — typed best-move endpoint (what the client apps consume)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_pool
from app.api.schemas import MoveRequest, MoveResponse
from app.config import get_settings
from app.engine.fen import InvalidFEN, validate_fen
from app.engine.manager import EnginePool, PoolExhausted, PoolNotReady
from app.engine.params import resolve_move_params
from app.engine.worker import EngineCrashed, EngineError, EngineTimeout
from app.logging import get_request_logger

router = APIRouter(tags=["engine"])
req_log = get_request_logger()


@router.post("/move", response_model=MoveResponse)
async def move(body: MoveRequest, pool: EnginePool = Depends(get_pool)) -> MoveResponse:
    settings = get_settings()
    started = time.perf_counter()

    try:
        fen = validate_fen(body.fen)
    except InvalidFEN as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        skill, movetime = resolve_move_params(
            skill_level=body.skill_level,
            movetime_ms=body.movetime_ms,
            difficulty=body.difficulty,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        async with pool.lease() as worker:
            engine_id = worker.id
            bestmove = await worker.analyse(fen, skill, movetime)
    except PoolExhausted as exc:
        raise HTTPException(status_code=503, detail="No engine available, try again") from exc
    except PoolNotReady as exc:
        raise HTTPException(status_code=503, detail="Engine pool not ready") from exc
    except EngineTimeout as exc:
        raise HTTPException(status_code=504, detail="Engine search timed out") from exc
    except (EngineCrashed, EngineError) as exc:
        raise HTTPException(status_code=503, detail="Engine error") from exc

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    req_log.info(
        "move",
        extra={
            "endpoint": "move",
            "fen": fen,
            "skill_level": skill,
            "movetime_ms": movetime,
            "bestmove": bestmove,
            "engine_id": engine_id,
            "latency_ms": latency_ms,
            "status": 200,
        },
    )
    return MoveResponse(bestmove=bestmove)
