"""The engine pool: a fixed set of Stockfish workers fronted by an asyncio queue.

The queue is the lease/semaphore — a request leases one idle worker, uses it, and returns
it. A worker that crashes or times out mid-request is NOT returned; it is replaced by a
freshly spawned, warmed worker so the pool size stays constant.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config import Settings
from app.engine.worker import EngineCrashed, EngineError, EngineTimeout, EngineWorker
from app.logging import get_app_logger

log = get_app_logger()


class PoolExhausted(Exception):
    """No engine became available within the acquire timeout."""


class PoolNotReady(Exception):
    """The pool has no live engines."""


class EnginePool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._idle: asyncio.Queue[EngineWorker] = asyncio.Queue()
        self._workers: list[EngineWorker] = []
        self._next_index = 0
        self._closed = False
        self._spawn_lock = asyncio.Lock()

    # --- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Spawn and warm the configured number of workers concurrently."""
        results = await asyncio.gather(
            *(self._spawn() for _ in range(self.settings.engine_pool_size)),
            return_exceptions=True,
        )
        for res in results:
            if isinstance(res, BaseException):
                log.warning("engine_spawn_failed", extra={"error": repr(res)})
        if not self._workers:
            raise PoolNotReady("no engines could be started")
        log.info(
            "engine_pool_started",
            extra={"alive": len(self._workers), "requested": self.settings.engine_pool_size},
        )

    async def shutdown(self) -> None:
        """Stop every worker with a bounded deadline."""
        self._closed = True
        await asyncio.gather(
            *(w.stop() for w in self._workers), return_exceptions=True
        )
        self._workers.clear()
        log.info("engine_pool_shutdown")

    async def _spawn(self) -> EngineWorker:
        async with self._spawn_lock:
            index = self._next_index
            self._next_index += 1
        worker = EngineWorker(self.settings, index)
        await worker.start()
        await worker.warmup()
        self._workers.append(worker)
        await self._idle.put(worker)
        return worker

    # --- introspection -------------------------------------------------------

    @property
    def pool_size(self) -> int:
        return self.settings.engine_pool_size

    @property
    def engines_alive(self) -> int:
        return sum(1 for w in self._workers if w.alive)

    def sample_worker(self) -> EngineWorker | None:
        """Return any worker (for reporting engine name/author). May be None."""
        return self._workers[0] if self._workers else None

    # --- leasing -------------------------------------------------------------

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[EngineWorker]:
        """Lease an idle worker; replace it on crash/timeout instead of returning it."""
        if self._closed:
            raise PoolNotReady("pool is shutting down")
        try:
            worker = await asyncio.wait_for(
                self._idle.get(), timeout=self.settings.pool_acquire_timeout_s
            )
        except TimeoutError as exc:
            raise PoolExhausted("no engine available") from exc

        healthy = True
        try:
            yield worker
        except (TimeoutError, EngineCrashed, EngineTimeout, EngineError):
            healthy = False
            raise
        finally:
            if healthy and worker.alive and not self._closed:
                await self._idle.put(worker)
            else:
                # Drop the wedged/dead worker and bring up a replacement.
                await self._replace(worker)

    async def _replace(self, worker: EngineWorker) -> None:
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        await worker.stop()
        if self._closed:
            return
        try:
            await self._spawn()
            log.info("engine_replaced", extra={"engine_id": worker.id})
        except Exception as exc:  # noqa: BLE001 - log and continue; pool may be degraded
            log.error("engine_replace_failed", extra={"engine_id": worker.id, "error": repr(exc)})
