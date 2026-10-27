"""Analysis pipeline, steps 1–4.

1 JD extraction  ─► quote check ─► IDs assigned here
2 ranking        ─► ID coverage                      (after 1)
3 CV extraction  ─► quote check ─► IDs assigned here (in parallel with 1–2)
4 matching       ─► ID coverage ─► evidence check
Every step result is cached; progress goes to the SSE event bus.
"""

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any, Awaitable, Callable

from .. import db
from ..checks.integrity import check_coverage
from ..checks.quotes import Dropped, verify_match_evidence, verify_quotes
from ..config import get_settings
from ..llm.client import LLMError, call_tool, data_block
from ..llm.prompts import steps as P
from ..schemas import CVItem, JDItem, MatchLLM, RankedRequirement
from . import events
from .cache import cache_key

log = logging.getLogger(__name__)

STEP_LABELS = {
    "jd": "Extracting job requirements",
    "rank": "Ranking requirements",
    "resume": "Extracting resume",
    "match": "Matching resume to requirements",
}
CATEGORY_PREFIX = {"task": "T", "requirement": "R", "nice_to_have": "N"}

_running: dict[int, asyncio.Task] = {}


def load_inputs(analysis_id: int) -> dict[str, Any]:
    row = db.one(
        "SELECT a.*, r.text AS resume_text, j.text AS jd_text, j.url AS jd_url"
        " FROM analyses a JOIN resumes r ON r.id = a.resume_id JOIN job_postings j ON j.id = a.jd_id"
        " WHERE a.id = ?",
        (analysis_id,),
    )
    if row is None:
        raise KeyError(analysis_id)
    return row


def _usage_event(analysis_id: int) -> None:
    events.emit(analysis_id, "usage", db.analysis_cost(analysis_id))


async def run_step(
    analysis_id: int, step: str, key: str,
    compute: Callable[[], Awaitable[tuple[Any, list[Dropped]]]],
) -> Any:
    events.emit(analysis_id, "step_started", {"step": step, "label": STEP_LABELS.get(step, step)})
    cached = db.get_step(key)
    if cached is not None:
        events.emit(analysis_id, "step_done", {"step": step, "cached": True,
                                               "dropped": len(cached["dropped"])})
        return cached["output"]
    output, dropped = await compute()
    dropped_dicts = [asdict(d) for d in dropped]
    db.put_step(key, step, P.VERSION[step], get_settings().anthropic_model, output, dropped_dicts)
    for d in dropped_dicts:
        events.emit(analysis_id, "item_dropped", d)
    events.emit(analysis_id, "step_done", {"step": step, "cached": False, "dropped": len(dropped)})
    _usage_event(analysis_id)
    return output


# --- step 1 -------------------------------------------------------------------

def assign_jd_ids(items: list) -> list[JDItem]:
    counters = {"T": 0, "R": 0, "N": 0}
    out = []
    for it in items:
        prefix = CATEGORY_PREFIX[it.category]
        counters[prefix] += 1
        out.append(JDItem(id=f"JD-{prefix}{counters[prefix]:02d}", **it.model_dump()))
    return out


async def step_jd(analysis_id: int, inp: dict) -> dict:
    jd_text, url = inp["jd_text"], inp["jd_url"]

    async def compute():
        s = get_settings()
        raw = await call_tool(P.JD_TOOL, P.jd_extraction(), data=data_block(jd_text, None, url),
                              step="jd", effort=s.effort("extract"), analysis_id=analysis_id)
        items = verify_quotes(raw.items, jd_text, "jd")
        about = verify_quotes(raw.about_company, jd_text, "jd", get_quote=lambda q: q)
        output = {
            "meta": {k: getattr(raw, k) for k in ("role_title", "company_name", "location", "employment_type")},
            "about_company": about.kept,
            "items": [i.model_dump() for i in assign_jd_ids(items.kept)],
        }
        if not output["items"]:
            raise LLMError("No job requirement could be verified against the posting text.")
        return output, items.dropped + about.dropped

    return await run_step(analysis_id, "jd", cache_key("jd", jd_text), compute)


# --- step 2 -------------------------------------------------------------------

async def step_rank(analysis_id: int, inp: dict, jd: dict) -> dict:
    items = jd["items"]
    ids = [i["id"] for i in items]

    async def compute():
        s = get_settings()
        raw = await call_tool(P.RANK_TOOL, P.ranking(items), data=data_block(inp["jd_text"], None, inp["jd_url"]),
                              step="rank", effort=s.effort("rank"), analysis_id=analysis_id)
        by_id, missing, dropped = check_coverage(raw.rankings, ids, "rank")
        areas = list(raw.skill_areas)
        if missing:
            if "Other" not in areas:
                areas.append("Other")
            for jd_id in missing:
                by_id[jd_id] = RankedRequirement(jd_id=jd_id, tier=4, reason="Not ranked by the model (default).",
                                                 skill_area="Other")
        output = {"skill_areas": areas,
                  "rankings": {k: v.model_dump() for k, v in by_id.items()},
                  "defaulted": missing}
        return output, dropped

    return await run_step(analysis_id, "rank", cache_key("rank", inp["jd_text"], items), compute)


# --- step 3 -------------------------------------------------------------------

async def step_resume(analysis_id: int, inp: dict) -> dict:
    resume_text = inp["resume_text"]

    async def compute():
        s = get_settings()
        raw = await call_tool(P.RESUME_TOOL, P.resume_extraction(), data=data_block(None, resume_text),
                              step="resume", effort=s.effort("extract"), analysis_id=analysis_id)
        checked = verify_quotes(raw.items, resume_text, "resume")
        items = [CVItem(id=f"CV-{n:02d}", **it.model_dump()) for n, it in enumerate(checked.kept, 1)]
        if not items:
            raise LLMError("No resume line could be verified against the resume text.")
        return {"items": [i.model_dump() for i in items]}, checked.dropped

    return await run_step(analysis_id, "resume", cache_key("resume", resume_text), compute)


# --- step 4 -------------------------------------------------------------------

async def step_match(analysis_id: int, inp: dict, jd: dict, rank: dict, cv: dict) -> dict:
    items, cv_items = jd["items"], cv["items"]
    ids = [i["id"] for i in items]

    async def compute():
        s = get_settings()
        raw = await call_tool(
            P.MATCH_TOOL, P.matching(items, rank["rankings"], cv_items),
            data=data_block(inp["jd_text"], inp["resume_text"], inp["jd_url"]),
            step="match", effort=s.effort("match"), analysis_id=analysis_id,
        )
        by_id, missing, dropped = check_coverage(raw.matches, ids, "match")
        for jd_id in missing:
            by_id[jd_id] = MatchLLM(jd_id=jd_id, status="gap", evidence=[], confidence=0.0,
                                    rationale="Not matched by the model (default).")
        cv_quotes = {c["id"]: c["quote"] for c in cv_items}
        matches, ev_dropped = verify_match_evidence([by_id[i] for i in ids], inp["resume_text"], cv_quotes)
        output = {"matches": {m.jd_id: m.model_dump() for m in matches}, "defaulted": missing}
        return output, dropped + ev_dropped

    tiers = {k: v["tier"] for k, v in rank["rankings"].items()}
    key = cache_key("match", inp["jd_text"], inp["resume_text"], items, tiers, cv_items)
    return await run_step(analysis_id, "match", key, compute)


# --- orchestration --------------------------------------------------------------

async def run_analysis(analysis_id: int) -> None:
    inp = load_inputs(analysis_id)
    events.reset(analysis_id)
    db.execute("UPDATE analyses SET status = 'running', error = NULL, updated_at = ? WHERE id = ?",
               (db.now(), analysis_id))
    events.emit(analysis_id, "analysis_started", {"analysis_id": analysis_id})
    try:
        async def jd_then_rank():
            jd = await step_jd(analysis_id, inp)
            return jd, await step_rank(analysis_id, inp, jd)

        (jd, rank), cv = await asyncio.gather(jd_then_rank(), step_resume(analysis_id, inp))
        match = await step_match(analysis_id, inp, jd, rank, cv)
        result = {"jd": jd, "rank": rank, "resume": cv, "match": match}
        db.execute("UPDATE analyses SET status = 'done', result_json = ?, updated_at = ? WHERE id = ?",
                   (json.dumps(result), db.now(), analysis_id))
        _usage_event(analysis_id)
        events.emit(analysis_id, "analysis_done", {"analysis_id": analysis_id})
        from .topic_queue import queue  # local import: topic_queue imports this module

        queue.enqueue_prefetch(analysis_id)
    except Exception as e:  # any failure ends the run; the UI offers a retry
        message = str(e) if isinstance(e, LLMError) else f"Unexpected error: {type(e).__name__}: {e}"
        log.exception("Analysis %s failed", analysis_id)
        db.execute("UPDATE analyses SET status = 'error', error = ?, updated_at = ? WHERE id = ?",
                   (message, db.now(), analysis_id))
        events.emit(analysis_id, "pipeline_error", {"message": message})
    finally:
        _running.pop(analysis_id, None)


def start(analysis_id: int) -> None:
    if analysis_id in _running and not _running[analysis_id].done():
        return
    _running[analysis_id] = asyncio.create_task(run_analysis(analysis_id))


def is_running(analysis_id: int) -> bool:
    return analysis_id in _running and not _running[analysis_id].done()


def load_result(analysis_id: int) -> dict | None:
    row = db.one("SELECT result_json FROM analyses WHERE id = ?", (analysis_id,))
    return json.loads(row["result_json"]) if row and row["result_json"] else None


def all_dropped(result: dict, inp: dict) -> list[dict]:
    """Dropped items of the cached steps, for the transparency panel."""
    keys = [
        cache_key("jd", inp["jd_text"]),
        cache_key("rank", inp["jd_text"], result["jd"]["items"]),
        cache_key("resume", inp["resume_text"]),
        cache_key("match", inp["jd_text"], inp["resume_text"], result["jd"]["items"],
                  {k: v["tier"] for k, v in result["rank"]["rankings"].items()}, result["resume"]["items"]),
    ]
    out: list[dict] = []
    for k in keys:
        cached = db.get_step(k)
        if cached:
            out.extend(cached["dropped"])
    return out
