"""Fire-and-forget background tasks that are not garbage-collected mid-run.

The event loop only keeps weak references to tasks, so a bare
``asyncio.create_task(...)`` whose result is dropped can disappear before it
finishes. ``run_in_background`` holds a strong reference until it completes.
"""

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task] = set()


def run_in_background(coro: Coroutine, name: str | None = None) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)

    def _done(t: asyncio.Task):
        _tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error(f"Background task {t.get_name()} failed", exc_info=t.exception())

    task.add_done_callback(_done)
    return task
