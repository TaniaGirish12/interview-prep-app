"""ID integrity: anything that references a JD id that step 1 did not produce is dropped."""

import logging
from typing import Iterable, TypeVar

from ..schemas import GapPlan, TopicContentLLM
from .quotes import Dropped

log = logging.getLogger(__name__)
T = TypeVar("T")  # RankedRequirement, MatchLLM or Match: anything with a jd_id


def _drop(step: str, reason: str, item: dict) -> Dropped:
    log.warning("Dropped %s item (%s): %s", step, reason, item)
    return Dropped(step, reason, item)


def check_coverage(
    items: Iterable[T], jd_ids: list[str], step: str
) -> tuple[dict[str, T], list[str], list[Dropped]]:
    """Keep the first entry per known JD id. Returns (by_id, missing_ids, dropped)."""
    known = set(jd_ids)
    by_id: dict[str, T] = {}
    dropped: list[Dropped] = []
    for it in items:
        if it.jd_id not in known:
            dropped.append(_drop(step, f"unknown JD id {it.jd_id}", it.model_dump()))
        elif it.jd_id in by_id:
            dropped.append(_drop(step, f"duplicate JD id {it.jd_id}", it.model_dump()))
        else:
            by_id[it.jd_id] = it
    missing = [i for i in jd_ids if i not in by_id]
    return by_id, missing, dropped


def _filter_ids(ids: list[str], known: set[str]) -> list[str]:
    return [i for i in ids if i in known]


def check_topic(topic: TopicContentLLM, known: set[str]) -> tuple[TopicContentLLM | None, list[Dropped]]:
    """Strip unknown ids from every item; drop items left with no traceable id."""
    dropped: list[Dropped] = []
    if topic.jd_id not in known:
        return None, [_drop("topic", f"unknown JD id {topic.jd_id}", {"jd_id": topic.jd_id})]

    def keep(items: list, kind: str) -> list:
        out = []
        for it in items:
            ids = _filter_ids(it.jd_ids, known)
            if ids:
                out.append(it.model_copy(update={"jd_ids": ids}))
            else:
                dropped.append(_drop("topic", f"{kind} cites no known JD id", it.model_dump()))
        return out

    cleaned = topic.model_copy(update={
        "code_examples": keep(topic.code_examples, "code example"),
        "common_mistakes": keep(topic.common_mistakes, "mistake"),
        "real_world_use": keep(topic.real_world_use, "real-world use"),
        "likely_questions": keep(topic.likely_questions, "question"),
    })
    return cleaned, dropped


def check_gap_plans(plans: list[GapPlan], allowed: set[str], known: set[str]) -> tuple[list[GapPlan], list[Dropped]]:
    out: list[GapPlan] = []
    dropped: list[Dropped] = []
    seen: set[str] = set()
    for p in plans:
        if p.jd_id not in allowed or p.jd_id in seen:
            dropped.append(_drop("gaps", f"unexpected or duplicate JD id {p.jd_id}", p.model_dump()))
            continue
        steps = []
        for s in p.steps:
            ids = _filter_ids(s.jd_ids, known)
            if ids:
                steps.append(s.model_copy(update={"jd_ids": ids}))
            else:
                dropped.append(_drop("gaps", "step cites no known JD id", s.model_dump()))
        if steps:
            seen.add(p.jd_id)
            out.append(p.model_copy(update={"steps": steps}))
    return out, dropped

