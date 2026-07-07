"""AsyncioExecutor: background wrapper tasks must be strongly referenced (no GC
mid-flight) and the task loop must exit on the shutdown sentinel without polling."""
from __future__ import annotations

import asyncio

from app.threads.asyncio_executor import AsyncTask, AsyncioExecutor, TaskSignals


def test_process_tasks_tracks_and_releases_background_tasks():
    """Each submitted task is held in _background_tasks until it completes, then
    the done-callback discards it (so the set doesn't leak)."""

    async def scenario():
        ex = AsyncioExecutor()
        ex._task_queue = asyncio.Queue()

        ran = asyncio.Event()

        async def work():
            ran.set()
            return "ok"

        sig = TaskSignals()
        await ex._task_queue.put(
            AsyncTask(task_id=1, coro=work(), signals=sig)
        )
        await ex._task_queue.put(None)  # shutdown sentinel

        # _process_tasks must return promptly on the sentinel (blocking get,
        # no 100ms polling). Guard with a timeout so a regression to a hung
        # loop fails loudly instead of hanging the suite.
        await asyncio.wait_for(ex._process_tasks(), timeout=2.0)

        # The wrapper was scheduled and is held strongly (not yet run: it runs
        # after _process_tasks returns). This is exactly the GC window the fix
        # protects — without the strong ref the task could be collected here.
        assert len(ex._background_tasks) == 1
        # Let the scheduled wrapper run and fire its done-callback.
        await asyncio.sleep(0.05)
        assert ran.is_set()
        assert len(ex._background_tasks) == 0

    asyncio.run(scenario())


def test_sentinel_exits_immediately_when_idle():
    """A pure sentinel (no work) exits at once — proves we block on get() and
    are woken by the sentinel rather than a timeout tick."""

    async def scenario():
        ex = AsyncioExecutor()
        ex._task_queue = asyncio.Queue()
        await ex._task_queue.put(None)
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        await asyncio.wait_for(ex._process_tasks(), timeout=1.0)
        # Should be near-instant; generous bound just guards against a hang.
        assert loop.time() - t0 < 0.5

    asyncio.run(scenario())
