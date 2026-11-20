import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable

from config.computing import COMPUTING_SETTINGS, ComputingSettings


class CPUWorker:
    """Runs CPU-bound, pickleable callables in isolated worker processes."""

    def __init__(self, settings: ComputingSettings = COMPUTING_SETTINGS):
        self._executor = ProcessPoolExecutor(
            max_workers=settings.max_cpu_workers
        )
        self._closed = False

    async def run(
        self,
        handler: Callable[..., Any],
        payload: Any,
    ) -> Any:
        if self._closed:
            raise RuntimeError("CPUWorker is shut down.")

        loop = asyncio.get_running_loop()
        if isinstance(payload, tuple):
            future = loop.run_in_executor(self._executor, handler, *payload)
        elif isinstance(payload, dict):
            future = loop.run_in_executor(self._executor, handler, **payload)
        else:
            future = loop.run_in_executor(self._executor, handler, payload)

        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # ProcessPoolExecutor cannot reliably terminate a running callable.
            # Keep the scheduler slot occupied until the process has finished.
            try:
                await asyncio.shield(future)
            except Exception:
                pass
            raise

    async def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(
            self._executor.shutdown,
            wait=True,
            cancel_futures=True,
        )
