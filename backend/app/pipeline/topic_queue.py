"""Background topic generation.

Tier 1 and 2 topics are pre-generated in study-next order once an analysis
finishes. Opening a topic moves it to the front of the queue. Results are cached
by topics.generate_topic, so a topic is never generated twice.
"""

import asyncio
import itertools
import logging

from .. import db
from ..checks.scoring import compute_scores
from ..config import get_settings
from ..schemas import JDItem, Match, RankedRequirement
from . import events
from .runner import load_result
from .topics import generate_topic, get_cached_topic

log = logging.getLogger(__name__)
Key = tuple[int, str]


class TopicQueue:
    def __init__(self) -> None:
        self.pending: dict[Key, float] = {}
        self.status: dict[Key, str] = {}
        self.errors: dict[Key, str] = {}
        self._cond: asyncio.Condition | None = None
        self._workers: list[asyncio.Task] = []
        self._front = itertools.count()

    @property
    def cond(self) -> asyncio.Condition:
        if self._cond is None:
            self._cond = asyncio.Condition()
        return self._cond

    def start(self) -> None:
        for _ in range(get_settings().topic_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def _set(self, key: Key, status: str, error: str | None = None) -> None:
        self.status[key] = status
        if error:
            self.errors[key] = error
        else:
            self.errors.pop(key, None)
        events.emit(key[0], "topic_status", {"jd_id": key[1], "status": status, "error": error})

    def _put(self, key: Key, priority: float) -> None:
        if self.status.get(key) == "generating":
            return
        if key in self.pending:
            priority = min(priority, self.pending[key])
        self.pending[key] = priority
        self._set(key, "queued")
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify())

    async def _notify(self) -> None:
        async with self.cond:
            self.cond.notify_all()

    def open(self, analysis_id: int, jd_id: str) -> str:
        """Called when the user opens a topic. Returns its status after the call."""
        key = (analysis_id, jd_id)
        if get_cached_topic(analysis_id, jd_id) is not None:
            return "ready"
        if self.status.get(key) != "generating":
            self._put(key, -1e9 - next(self._front))  # most recently opened goes first
        return self.status[key]

    def enqueue_prefetch(self, analysis_id: int) -> None:
        result = load_result(analysis_id)
        if result is None:
            return
        items = [JDItem(**i) for i in result["jd"]["items"]]
        rankings = {k: RankedRequirement(**v) for k, v in result["rank"]["rankings"].items()}
        matches = {k: Match(**v) for k, v in result["match"]["matches"].items()}
        scores = compute_scores(items, rankings, matches, result["rank"]["skill_areas"])
        # The top N tier 1–2 topics in study-next order. Already generated ones count
        # toward N, so reopening an analysis never pulls in further topics.
        limit = get_settings().prefetch_topics
        candidates = [row for row in scores["study_next"] if row["tier"] <= 2][:limit]
        for n, row in enumerate(candidates):
            key = (analysis_id, row["jd_id"])
            if key in self.pending or self.status.get(key) in ("generating", "error"):
                continue
            if get_cached_topic(analysis_id, row["jd_id"]) is None:
                self._put(key, float(n))

    def status_of(self, analysis_id: int, jd_id: str) -> dict:
        key = (analysis_id, jd_id)
        if get_cached_topic(analysis_id, jd_id) is not None:
            return {"status": "ready"}
        status = self.status.get(key, "not_started")
        out: dict = {"status": status}
        if status == "queued":
            ordered = sorted(self.pending, key=self.pending.get)
            out["position"] = ordered.index(key) + 1 if key in ordered else None
        if status == "error":
            out["error"] = self.errors.get(key)
        return out

    async def _next(self) -> Key:
        async with self.cond:
            while not self.pending:
                await self.cond.wait()
            key = min(self.pending, key=self.pending.get)
            del self.pending[key]
            return key

    async def _worker(self) -> None:
        while True:
            key = await self._next()
            self._set(key, "generating")
            try:
                await generate_topic(*key)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # one failed topic must not stop the queue
                log.exception("Topic %s failed", key)
                self._set(key, "error", str(e))
                continue
            self._set(key, "ready")
            events.emit(key[0], "usage", db.analysis_cost(key[0]))


queue = TopicQueue()
