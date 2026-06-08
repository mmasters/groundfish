"""FastAPI application factory and lifespan wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes_health, routes_move, routes_uci
from app.config import get_settings
from app.engine.manager import EnginePool
from app.logging import configure_logging, get_app_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    log = get_app_logger()

    pool = EnginePool(settings)
    log.info("starting_engine_pool", extra={"engine_path": settings.engine_path})
    await pool.start()
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stockfish Engine Server",
        version="0.1.0",
        summary="Internal HTTP service wrapping native Stockfish (NNUE).",
        lifespan=lifespan,
    )
    app.include_router(routes_health.router)
    app.include_router(routes_move.router)
    app.include_router(routes_uci.router)
    return app


app = create_app()
