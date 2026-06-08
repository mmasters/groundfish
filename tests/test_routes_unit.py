"""Endpoint behavior with a mocked engine pool (no real Stockfish).

Async tests are collected automatically via ``asyncio_mode = "auto"`` (see pyproject).
"""

from app.engine.manager import PoolExhausted
from app.engine.worker import EngineTimeout
from tests.conftest import START_FEN, FakePool, FakeWorker


async def test_healthz(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["engines_alive"] == 1 and body["status"] == "ready"


async def test_engine_info(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.get("/engine/info")
    body = r.json()
    assert body["name"] == "Stockfish Fake"
    assert body["difficulty_presets"]["medium"] == [9, 600]


async def test_move_ok(client_factory):
    pool = FakePool(worker=FakeWorker(bestmove="d2d4"))
    async with client_factory(pool) as c:
        r = await c.post("/move", json={"fen": START_FEN, "difficulty": "medium"})
    assert r.status_code == 200
    assert r.json() == {"bestmove": "d2d4"}
    # difficulty 'medium' -> skill 9, movetime 600 reached the engine
    assert pool.worker.analyse_calls[-1] == (START_FEN, 9, 600)


async def test_move_clamps_movetime(client_factory):
    pool = FakePool()
    async with client_factory(pool) as c:
        r = await c.post("/move", json={"fen": START_FEN, "movetime_ms": 999999})
    assert r.status_code == 200
    # clamped to default max (2000)
    assert pool.worker.analyse_calls[-1][2] == 2000


async def test_move_bad_fen(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.post("/move", json={"fen": "totally-bogus"})
    assert r.status_code == 400


async def test_move_bad_difficulty(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.post("/move", json={"fen": START_FEN, "difficulty": "nope"})
    assert r.status_code == 422


async def test_move_skill_out_of_range_rejected_by_schema(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.post("/move", json={"fen": START_FEN, "skill_level": 99})
    assert r.status_code == 422


async def test_move_pool_exhausted(client_factory):
    pool = FakePool(lease_error=PoolExhausted("busy"))
    async with client_factory(pool) as c:
        r = await c.post("/move", json={"fen": START_FEN})
    assert r.status_code == 503


async def test_move_engine_timeout(client_factory):
    pool = FakePool(worker=FakeWorker(raises=EngineTimeout("slow")))
    async with client_factory(pool) as c:
        r = await c.post("/move", json={"fen": START_FEN})
    assert r.status_code == 504


async def test_uci_ok(client_factory):
    lines = ["info depth 5 score cp 31", "bestmove e2e4 ponder e7e5"]
    pool = FakePool(worker=FakeWorker(lines=lines))
    async with client_factory(pool) as c:
        r = await c.post(
            "/uci", json={"commands": [f"position fen {START_FEN}", "go movetime 300"]}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["bestmove"] == "e2e4"
    assert body["ponder"] == "e7e5"
    assert body["lines"] == lines


async def test_uci_rejects_quit(client_factory):
    async with client_factory(FakePool()) as c:
        r = await c.post("/uci", json={"commands": ["quit"]})
    assert r.status_code == 400
