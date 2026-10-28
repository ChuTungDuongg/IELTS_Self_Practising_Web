"""Run blocking storage work without abandoning an in-flight file operation."""

import asyncio


async def storage_io(operation, /, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Callers record newly written keys inside operation, so compensation can
        # run after the write finishes even when the request was cancelled.
        await asyncio.gather(task, return_exceptions=True)
        raise
