"""FEN validation and normalization.

Engine input is treated as untrusted: we reject oversized / non-printable / multi-line
input before it ever reaches the engine subprocess (blocks UCI command injection such as
embedding ``\\nquit``), then parse with python-chess and forward only the canonical FEN.
"""

from __future__ import annotations

import chess

# A legal FEN is comfortably under this; anything longer is malformed or hostile.
MAX_FEN_LENGTH = 100


class InvalidFEN(ValueError):
    """Raised when a FEN string fails validation."""


def validate_fen(fen: str) -> str:
    """Validate ``fen`` and return its normalized canonical form.

    Raises :class:`InvalidFEN` on any problem.
    """
    if not isinstance(fen, str):
        raise InvalidFEN("FEN must be a string")

    fen = fen.strip()
    if not fen:
        raise InvalidFEN("FEN is empty")
    if len(fen) > MAX_FEN_LENGTH:
        raise InvalidFEN(f"FEN exceeds maximum length of {MAX_FEN_LENGTH}")
    if not fen.isascii() or any(ord(c) < 0x20 for c in fen):
        raise InvalidFEN("FEN contains non-printable or non-ASCII characters")

    try:
        board = chess.Board(fen)
    except ValueError as exc:  # malformed structure / wrong field count
        raise InvalidFEN(f"Malformed FEN: {exc}") from exc

    if not board.is_valid():
        raise InvalidFEN(f"Illegal position: {board.status()!r}")

    return board.fen()
