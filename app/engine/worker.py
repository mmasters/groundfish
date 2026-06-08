"""A single Stockfish subprocess driven over the UCI protocol.

We manage the process directly with asyncio (rather than python-chess's high-level engine
API) so the same worker can serve both the typed ``/move`` path and the raw ``/uci``
command-batch passthrough uniformly. A per-worker lock guarantees only one command
sequence runs at a time — Stockfish is stateful and a search occupies the whole process.
"""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.logging import get_app_logger

log = get_app_logger()


class EngineError(Exception):
    """Base class for engine failures."""


class EngineCrashed(EngineError):
    """The engine process died (stdout closed / non-zero exit)."""


class EngineTimeout(EngineError):
    """The engine did not produce the expected output in time."""


def _first_word(line: str) -> str:
    return line.split(" ", 1)[0]


class EngineWorker:
    """Wraps one ``stockfish`` process and serializes UCI command sequences."""

    def __init__(self, settings: Settings, index: int) -> None:
        self.settings = settings
        self.index = index
        self.id = f"engine-{index}"
        self.name = "unknown"
        self.author = ""
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    # --- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Spawn the process, complete the UCI handshake, and configure options."""
        self._proc = await asyncio.create_subprocess_exec(
            self.settings.engine_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(
            self._handshake(), timeout=self.settings.engine_start_timeout_s
        )

    async def _handshake(self) -> None:
        self._write("uci")
        for line in await self._read_until("uciok", timeout=self.settings.engine_start_timeout_s):
            if line.startswith("id name "):
                self.name = line[len("id name "):]
            elif line.startswith("id author "):
                self.author = line[len("id author "):]
        self._write("setoption name Threads value 1")
        self._write(f"setoption name Hash value {self.settings.engine_hash_mb}")
        await self._sync(timeout=self.settings.engine_start_timeout_s)

    async def warmup(self) -> None:
        """Run a tiny search from the start position to fault in NNUE weights."""
        await self.analyse(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            skill=None,
            movetime_ms=max(self.settings.min_movetime_ms, 50),
        )

    async def ping(self) -> bool:
        """Return True if the engine answers ``isready`` promptly."""
        try:
            async with self._lock:
                self._ensure_alive()
                await self._sync(timeout=2.0)
            return True
        except (TimeoutError, EngineError, AssertionError):
            return False

    async def stop(self) -> None:
        """Best-effort graceful shutdown, escalating to kill."""
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.returncode is None and proc.stdin is not None and not proc.stdin.is_closing():
                self._write("quit")
                await asyncio.wait_for(proc.wait(), timeout=3.0)
        except (TimeoutError, ProcessLookupError, ConnectionResetError, ValueError):
            pass
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            self._proc = None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    # --- request handlers ----------------------------------------------------

    async def analyse(
        self, fen: str, skill: int | None, movetime_ms: int
    ) -> str | None:
        """Run a fixed-movetime search for ``fen``; return the best move (UCI) or None.

        ``None`` is returned for terminal positions where the engine reports
        ``bestmove (none)`` (checkmate / stalemate).
        """
        timeout = movetime_ms / 1000 + self.settings.engine_timeout_margin_s
        async with self._lock:
            self._ensure_alive()
            self._write("ucinewgame")
            if skill is not None:
                self._write(f"setoption name Skill Level value {skill}")
            self._write(f"position fen {fen}")
            self._write(f"go movetime {movetime_ms}")
            lines = await self._read_until("bestmove", timeout=timeout)
        move = lines[-1].split(" ")
        best = move[1] if len(move) > 1 else "(none)"
        return None if best == "(none)" else best

    async def run_commands(
        self, commands: list[str], terminal: str, timeout: float
    ) -> list[str]:
        """Replay a UCI command batch on a freshly-reset engine; collect output lines.

        ``terminal`` is the first word of the line that ends the batch (``bestmove`` or
        ``readyok``). The caller (``app.engine.uci``) is responsible for sanitizing the
        commands and choosing the terminal token.
        """
        async with self._lock:
            self._ensure_alive()
            self._write("ucinewgame")
            for cmd in commands:
                self._write(cmd)
            return await self._read_until(terminal, timeout=timeout)

    # --- low-level IO --------------------------------------------------------

    def _ensure_alive(self) -> None:
        if not self.alive or self._proc is None or self._proc.stdin is None:
            raise EngineCrashed(f"{self.id} is not running")

    def _write(self, cmd: str) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write((cmd + "\n").encode())

    async def _sync(self, timeout: float) -> None:
        self._write("isready")
        await self._read_until("readyok", timeout=timeout)

    async def _read_until(self, terminal: str, timeout: float) -> list[str]:
        """Read stdout lines until one whose first word == ``terminal``.

        Returns every non-empty line read, including the terminal line.
        Raises :class:`EngineTimeout` / :class:`EngineCrashed` on failure.
        """
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        collected: list[str] = []
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise EngineTimeout(f"{self.id}: timed out waiting for {terminal!r}")
            try:
                raw = await asyncio.wait_for(stdout.readline(), timeout=remaining)
            except TimeoutError as exc:
                raise EngineTimeout(
                    f"{self.id}: timed out waiting for {terminal!r}"
                ) from exc
            if raw == b"":
                raise EngineCrashed(f"{self.id}: stdout closed")
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            collected.append(line)
            if _first_word(line) == terminal:
                return collected
