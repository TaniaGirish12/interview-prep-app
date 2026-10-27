"""Knowledge-gaps learning plan: one LLM call over partial and gap requirements."""

import asyncio
import logging
from dataclasses import asdict

from .. import db
from ..checks.integrity import check_gap_plans
from ..checks.scoring import compute_scores
from ..config import get_settings
from ..llm.client import call_tool, data_block
from ..llm.prompts import steps as P
from ..schemas import JDItem, Match, RankedRequirement
from . import events
from .cache import cache_key
from .runner import load_inputs, load_result

log = logging.getLogger(__name__)

_tasks: dict[int, asyncio.Task] = {}
_errors: dict[int, str] = {}


def _context(analysis_id: int) -> tuple[dict, list[dict], str]:
    inp = load_inputs(analysis_id)
    result = load_result(analysis_id)
    if result is None:
        raise ValueError("The analysis has not finished yet.")
    items = {i["id"]: i for i in result["jd"]["items"]}
    rankings = result["rank"]["rankings"]
    matches = result["match"]["matches"]
    scores = compute_scores(
        [JDItem(**i) for i in items.values()],
        {k: RankedRequirement(**v) for k, v in rankings.items()},
        {k: Match(**v) for k, v in matches.items()},
        result["rank"]["skill_areas"],
    )
    rows = [
        {"id": s["jd_id"], "name": items[s["jd_id"]]["name"], "quote": items[s["jd_id"]]["quote"],
         "tier": s["tier"], "status": s["status"],
         "resume_evidence": [e["quote"] for e in matches[s["jd_id"]]["evidence"]]}
        for s in scores["study_next"] if s["status"] != "strong"
    ]
    return inp, rows, cache_key("gaps", inp["jd_text"], inp["resume_text"], rows)


def get_gaps(analysis_id: int) -> dict:
    inp, rows, key = _context(analysis_id)
    cached = db.get_step(key)
    if cached:
        return {"status": "ready", **cached["output"]}
    if not rows:
        return {"status": "ready", "plans": []}
    task = _tasks.get(analysis_id)
    if task and not task.done():
        return {"status": "generating"}
    if analysis_id in _errors:
        return {"status": "error", "error": _errors[analysis_id]}
    return {"status": "not_started"}


def start_gaps(analysis_id: int) -> None:
    task = _tasks.get(analysis_id)
    if task and not task.done():
        return
    _errors.pop(analysis_id, None)
    _tasks[analysis_id] = asyncio.create_task(_generate(analysis_id))


async def _generate(analysis_id: int) -> None:
    try:
        inp, rows, key = _context(analysis_id)
        if not rows or db.get_step(key):
            return
        raw = await call_tool(
            P.GAPS_TOOL, P.gaps(rows), data=data_block(inp["jd_text"], inp["resume_text"], inp["jd_url"]),
            step="gaps", effort=get_settings().effort("gaps"), analysis_id=analysis_id,
        )
        all_ids = {i["id"] for i in load_result(analysis_id)["jd"]["items"]}
        plans, dropped = check_gap_plans(raw.plans, {r["id"] for r in rows}, all_ids)
        order = {r["id"]: n for n, r in enumerate(rows)}
        plans.sort(key=lambda p: order[p.jd_id])
        db.put_step(key, "gaps", P.VERSION["gaps"], get_settings().anthropic_model,
                    {"plans": [p.model_dump() for p in plans]}, [asdict(d) for d in dropped])
        events.emit(analysis_id, "gaps_ready", {})
        events.emit(analysis_id, "usage", db.analysis_cost(analysis_id))
    except Exception as e:  # reported to the page, which offers a retry
        log.exception("Gap plan failed for analysis %s", analysis_id)
        _errors[analysis_id] = str(e)
