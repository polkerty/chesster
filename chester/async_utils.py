# chester/async_utils.py
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Iterable, Tuple, TypeVar

from tqdm import tqdm

K = TypeVar("K")
V = TypeVar("V")


async def async_map_progress(
    items: Iterable[K],
    worker: Callable[[K], Awaitable[V]],
    *,
    concurrency: int,
    desc: str,
    quiet: bool,
) -> Dict[K, V]:
    """
    Apply async worker over items with a semaphore + tqdm progress.
    Returns {item: result}. Exceptions propagate (fail-fast) by default.
    """
    sem = asyncio.Semaphore(max(1, int(concurrency)))

    async def _run_one(it: K) -> Tuple[K, V]:
        async with sem:
            return it, await worker(it)

    tasks = [asyncio.create_task(_run_one(it)) for it in items]
    out: Dict[K, V] = {}

    pbar = tqdm(total=len(tasks), disable=quiet, desc=desc)
    try:
        for fut in asyncio.as_completed(tasks):
            k, v = await fut
            out[k] = v
            pbar.update(1)
    finally:
        pbar.close()

    return out
