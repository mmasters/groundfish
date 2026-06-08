"""Integration tests that spawn a real Stockfish process.

Run with ``pytest -m integration``. Skipped automatically when no stockfish binary is
available (set ``STOCKFISH_ENGINE_PATH`` or install one).
"""

import asyncio

import chess
import pytest

from app.engine.uci import prepare_batch
from app.engine.worker import EngineError
from tests.conftest import START_FEN, make_settings, requires_stockfish

pytestmark = [pytest.mark.integration, requires_stockfish]


async def test_move_returns_legal_move(real_pool):
    async with real_pool.lease() as worker:
        best = await worker.analyse(START_FEN, skill=None, movetime_ms=300)
    board = chess.Board(START_FEN)
    assert chess.Move.from_uci(best) in board.legal_moves


async def test_engine_identity(real_pool):
    worker = real_pool.sample_worker()
    assert worker is not None
    assert "stockfish" in worker.name.lower()


async def test_mate_in_one_is_found(real_pool):
    # Back-rank mate: white rook a1 -> a8 is checkmate.
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    async with real_pool.lease() as worker:
        best = await worker.analyse(fen, skill=None, movetime_ms=500)
    assert best == "a1a8"


async def test_uci_passthrough_returns_bestmove(real_pool):
    settings = make_settings()
    cmds, terminal, timeout = prepare_batch(
        [f"position fen {START_FEN}", "go movetime 300"], settings
    )
    async with real_pool.lease() as worker:
        lines = await worker.run_commands(cmds, terminal, timeout)
    assert any(line.startswith("bestmove") for line in lines)


async def test_crash_recovery_respawns_worker(real_pool):
    assert real_pool.engines_alive == 1

    with pytest.raises((EngineError, asyncio.TimeoutError, AssertionError, Exception)):
        async with real_pool.lease() as worker:
            # Kill the process out from under the search.
            worker._proc.kill()
            await worker.analyse(START_FEN, skill=None, movetime_ms=300)

    # Pool should have replaced the dead worker.
    assert real_pool.engines_alive == 1
    async with real_pool.lease() as worker:
        best = await worker.analyse(START_FEN, skill=None, movetime_ms=300)
    assert chess.Move.from_uci(best) in chess.Board(START_FEN).legal_moves
