import pytest

from app.engine.fen import MAX_FEN_LENGTH, InvalidFEN, validate_fen

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_valid_start_position_normalizes():
    assert validate_fen(START_FEN) == START_FEN


def test_valid_midgame_position():
    fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    assert validate_fen(fen) == fen


def test_whitespace_trimmed():
    assert validate_fen(f"  {START_FEN}  ") == START_FEN


def test_empty_rejected():
    with pytest.raises(InvalidFEN):
        validate_fen("   ")


def test_oversized_rejected():
    with pytest.raises(InvalidFEN):
        validate_fen("8/" * MAX_FEN_LENGTH)


def test_newline_injection_rejected():
    # An embedded newline could smuggle a second UCI command (e.g. "\nquit").
    with pytest.raises(InvalidFEN):
        validate_fen(START_FEN + "\nquit")


def test_non_ascii_rejected():
    with pytest.raises(InvalidFEN):
        validate_fen(START_FEN.replace("w", "ω"))


def test_malformed_rejected():
    with pytest.raises(InvalidFEN):
        validate_fen("not a fen at all")


def test_illegal_position_rejected():
    # No kings on the board -> not a valid chess position.
    with pytest.raises(InvalidFEN):
        validate_fen("8/8/8/8/8/8/8/8 w - - 0 1")
