"""In-memory event bus per analysis, consumed by the SSE endpoint.

Each analysis keeps its event history so a client that connects late, or
reconnects, first receives everything that already happened.
"""

import asyncio
from collections import defaultdict
from typing import Any

MAX_HISTORY = 500

_history: dict[int, list[dict[str, Any]]] = defaultdict(list)
_subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)


def emit(analysis_id: int, event: str, data: dict[str, Any] | None = None) -> None:
    item = {"event": event, "data": data or {}}
    hist = _history[analysis_id]
    hist.append(item)
    if len(hist) > MAX_HISTORY:
        del hist[: len(hist) - MAX_HISTORY]
    for q in list(_subscribers[analysis_id]):
        q.put_nowait(item)


def reset(analysis_id: int) -> None:
    _history[analysis_id].clear()


def subscribe(analysis_id: int) -> tuple[list[dict[str, Any]], asyncio.Queue]:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers[analysis_id].add(q)
    return list(_history[analysis_id]), q


def unsubscribe(analysis_id: int, q: asyncio.Queue) -> None:
    _subscribers[analysis_id].discard(q)
