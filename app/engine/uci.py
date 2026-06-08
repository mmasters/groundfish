"""Sanitization and terminal-token logic for the stateless ``/uci`` passthrough.

Even though this server is internal-only, the passthrough still enforces hard caps so a
single request can't pin a CPU forever: ``go infinite`` and unbounded ``go`` are rewritten
to a capped ``movetime``, ``go movetime N`` is clamped, ``quit`` is rejected, and a
wall-clock backstop (chosen by :func:`prepare_batch`) lets the pool kill+respawn a runaway.
"""

from __future__ import annotations

from app.config import Settings

MAX_COMMANDS = 64
MAX_COMMAND_LENGTH = 256

# Commands that would terminate or destabilize a pooled engine are not allowed through.
_FORBIDDEN = {"quit"}

# Tokens that bound a `go` search. If a `go` has none of these, we inject a movetime cap.
_GO_LIMIT_TOKENS = {"movetime", "depth", "nodes", "mate", "infinite"}


class InvalidUCIBatch(ValueError):
    """Raised when a /uci command batch is malformed or disallowed."""


def _sanitize_line(cmd: str) -> str:
    if not isinstance(cmd, str):
        raise InvalidUCIBatch("each command must be a string")
    cmd = cmd.strip()
    if not cmd:
        raise InvalidUCIBatch("empty command")
    if len(cmd) > MAX_COMMAND_LENGTH:
        raise InvalidUCIBatch(f"command exceeds {MAX_COMMAND_LENGTH} chars")
    if not cmd.isascii() or any(ord(c) < 0x20 for c in cmd):
        raise InvalidUCIBatch("command contains non-printable or non-ASCII characters")
    if cmd.split(" ", 1)[0] in _FORBIDDEN:
        raise InvalidUCIBatch(f"command not allowed: {cmd.split(' ', 1)[0]!r}")
    return cmd


def _cap_go(cmd: str, settings: Settings) -> str:
    """Rewrite a ``go`` command so its search is time-bounded within configured limits."""
    tokens = cmd.split()
    # `go` with no recognized limit -> add a default capped movetime.
    if not any(t in _GO_LIMIT_TOKENS for t in tokens[1:]):
        return f"go movetime {settings.default_movetime_ms}"

    out: list[str] = ["go"]
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok == "infinite":
            out += ["movetime", str(settings.max_movetime_ms)]
            i += 1
        elif tok == "movetime" and i + 1 < len(tokens):
            try:
                val = int(tokens[i + 1])
            except ValueError as exc:
                raise InvalidUCIBatch("movetime must be an integer") from exc
            val = max(settings.min_movetime_ms, min(settings.max_movetime_ms, val))
            out += ["movetime", str(val)]
            i += 2
        else:
            out.append(tok)
            i += 1
    return " ".join(out)


def prepare_batch(
    commands: list[str], settings: Settings
) -> tuple[list[str], str, float]:
    """Validate + cap a command batch and pick its terminal token and timeout.

    Returns ``(safe_commands, terminal_token, timeout_seconds)``. A backstop ``isready``
    is appended when the batch produces no naturally-terminating output, so the read
    always completes deterministically.
    """
    if not isinstance(commands, list) or not commands:
        raise InvalidUCIBatch("commands must be a non-empty list")
    if len(commands) > MAX_COMMANDS:
        raise InvalidUCIBatch(f"too many commands (max {MAX_COMMANDS})")

    safe: list[str] = []
    has_go = False
    for raw in commands:
        cmd = _sanitize_line(raw)
        if cmd.split(" ", 1)[0] == "go":
            cmd = _cap_go(cmd, settings)
            has_go = True
        safe.append(cmd)

    if has_go:
        terminal = "bestmove"
        timeout = settings.max_movetime_ms / 1000 + settings.engine_timeout_margin_s
    else:
        # No search -> these commands emit no terminating line; force a sync point.
        safe.append("isready")
        terminal = "readyok"
        timeout = settings.engine_start_timeout_s
    return safe, terminal, timeout


def parse_result(lines: list[str]) -> tuple[str | None, str | None]:
    """Extract ``(bestmove, ponder)`` from engine output lines, if present."""
    for line in reversed(lines):
        parts = line.split()
        if parts and parts[0] == "bestmove":
            best = parts[1] if len(parts) > 1 else None
            if best == "(none)":
                best = None
            ponder = None
            if "ponder" in parts:
                pi = parts.index("ponder")
                if pi + 1 < len(parts):
                    ponder = parts[pi + 1]
            return best, ponder
    return None, None
