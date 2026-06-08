"""Shared test fixtures: a settings factory, fake-pool HTTP client, and a gated
real-engine pool for integration tests."""

from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager

import pytest

from app.config import Settings
from app.engine.manager import EnginePool

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def make_settings(**overrides) -> Settings:
    base = dict(
        engine_pool_size=1,
        log_file="",          # no file handler in tests
        log_to_stdout=False,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


# --- fake engine pool (unit tests) ------------------------------------------


class FakeWorker:
    def __init__(self, *, bestmove="e2e4", lines=None, raises=None):
        self.id = "engine-fake"
        self.name = "Stockfish Fake"
        self.author = "tests"
        self.alive = True
        self._bestmove = bestmove
        self._lines = lines if lines is not None else ["bestmove e2e4 ponder e7e5"]
        self._raises = raises
        self.analyse_calls: list[tuple] = []
        self.command_calls: list[tuple] = []

    async def analyse(self, fen, skill, movetime_ms):
        self.analyse_calls.append((fen, skill, movetime_ms))
        if self._raises is not None:
            raise self._raises
        return self._bestmove

    async def run_commands(self, commands, terminal, timeout):
        self.command_calls.append((commands, terminal, timeout))
        if self._raises is not None:
            raise self._raises
        return list(self._lines)


class FakePool:
    def __init__(self, *, worker=None, lease_error=None):
        self.worker = worker or FakeWorker()
        self._lease_error = lease_error

    @property
    def pool_size(self) -> int:
        return 1

    @property
    def engines_alive(self) -> int:
        return 1

    def sample_worker(self):
        return self.worker

    @asynccontextmanager
    async def lease(self):
        if self._lease_error is not None:
            raise self._lease_error
        yield self.worker


@pytest.fixture
def client_factory():
    """Return a callable that builds an httpx AsyncClient backed by a fake pool.

    Uses ASGITransport (no lifespan), so no real engine is spawned; the pool dependency
    is overridden directly.
    """
    import httpx

    from app.api.deps import get_pool
    from app.main import create_app

    created = []

    def _make(pool) -> httpx.AsyncClient:
        app = create_app()
        app.dependency_overrides[get_pool] = lambda: pool
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        created.append(client)
        return client

    yield _make


# --- real engine pool (integration tests) -----------------------------------


def _stockfish_path() -> str | None:
    return os.environ.get("STOCKFISH_ENGINE_PATH") or shutil.which("stockfish")


requires_stockfish = pytest.mark.skipif(
    _stockfish_path() is None,
    reason="no stockfish binary found (set STOCKFISH_ENGINE_PATH or install stockfish)",
)


@pytest.fixture
async def real_pool():
    path = _stockfish_path()
    if path is None:
        pytest.skip("no stockfish binary")
    pool = EnginePool(make_settings(engine_path=path, engine_pool_size=1))
    await pool.start()
    try:
        yield pool
    finally:
        await pool.shutdown()
