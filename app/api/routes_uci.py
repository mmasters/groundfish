"""POST /uci — stateless UCI command-batch passthrough."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_pool
from app.api.schemas import UCIRequest, UCIResponse
from app.config import get_settings
from app.engine.manager import EnginePool, PoolExhausted, PoolNotReady
from app.engine.uci import InvalidUCIBatch, parse_result, prepare_batch
from app.engine.worker import EngineCrashed, EngineError, EngineTimeout
from app.logging import get_request_logger

router = APIRouter(tags=["engine"])
req_log = get_request_logger()


@router.post("/uci", response_model=UCIResponse)
async def uci(body: UCIRequest, pool: EnginePool = Depends(get_pool)) -> UCIResponse:
    settings = get_settings()
    started = time.perf_counter()

    try:
        commands, terminal, timeout = prepare_batch(body.commands, settings)
    except InvalidUCIBatch as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        async with pool.lease() as worker:
            engine_id = worker.id
            lines = await worker.run_commands(commands, terminal, timeout)
    except PoolExhausted as exc:
        raise HTTPException(status_code=503, detail="No engine available, try again") from exc
    except PoolNotReady as exc:
        raise HTTPException(status_code=503, detail="Engine pool not ready") from exc
    except EngineTimeout as exc:
        raise HTTPException(status_code=504, detail="Engine command timed out") from exc
    except (EngineCrashed, EngineError) as exc:
        raise HTTPException(status_code=503, detail="Engine error") from exc

    bestmove, ponder = parse_result(lines)
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    req_log.info(
        "uci",
        extra={
            "endpoint": "uci",
            "commands": commands,
            "bestmove": bestmove,
            "ponder": ponder,
            "engine_id": engine_id,
            "latency_ms": latency_ms,
            "status": 200,
        },
    )
    return UCIResponse(lines=lines, bestmove=bestmove, ponder=ponder)
