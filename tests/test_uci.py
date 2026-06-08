import pytest

from app.engine.uci import InvalidUCIBatch, parse_result, prepare_batch
from tests.conftest import make_settings

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_go_infinite_is_capped():
    s = make_settings(max_movetime_ms=2000)
    cmds, terminal, _ = prepare_batch([f"position fen {FEN}", "go infinite"], s)
    assert cmds[-1] == "go movetime 2000"
    assert terminal == "bestmove"


def test_unbounded_go_gets_default_movetime():
    s = make_settings(default_movetime_ms=600)
    cmds, terminal, _ = prepare_batch([f"position fen {FEN}", "go"], s)
    assert cmds[-1] == "go movetime 600"
    assert terminal == "bestmove"


def test_movetime_is_clamped():
    s = make_settings(min_movetime_ms=50, max_movetime_ms=2000)
    cmds, _, _ = prepare_batch(["go movetime 999999"], s)
    assert cmds[-1] == "go movetime 2000"
    cmds, _, _ = prepare_batch(["go movetime 1"], s)
    assert cmds[-1] == "go movetime 50"


def test_depth_go_is_preserved():
    s = make_settings()
    cmds, terminal, _ = prepare_batch([f"position fen {FEN}", "go depth 5"], s)
    assert cmds[-1] == "go depth 5"
    assert terminal == "bestmove"


def test_no_search_appends_isready_sync():
    s = make_settings()
    cmds, terminal, _ = prepare_batch([f"position fen {FEN}"], s)
    assert cmds[-1] == "isready"
    assert terminal == "readyok"


def test_quit_is_rejected():
    s = make_settings()
    with pytest.raises(InvalidUCIBatch):
        prepare_batch(["quit"], s)


def test_newline_injection_rejected():
    s = make_settings()
    with pytest.raises(InvalidUCIBatch):
        prepare_batch([f"position fen {FEN}\nquit"], s)


def test_empty_batch_rejected():
    s = make_settings()
    with pytest.raises(InvalidUCIBatch):
        prepare_batch([], s)


def test_too_many_commands_rejected():
    s = make_settings()
    with pytest.raises(InvalidUCIBatch):
        prepare_batch(["isready"] * 1000, s)


def test_parse_result_extracts_bestmove_and_ponder():
    lines = ["info depth 1 score cp 20", "bestmove e2e4 ponder e7e5"]
    assert parse_result(lines) == ("e2e4", "e7e5")


def test_parse_result_handles_none():
    assert parse_result(["bestmove (none)"]) == (None, None)


def test_parse_result_missing():
    assert parse_result(["info string hello"]) == (None, None)
