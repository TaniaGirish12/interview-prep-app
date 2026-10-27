"""Step 5: topic notes for one requirement, with ID integrity and code checks."""

import logging
from dataclasses import asdict

from .. import db
from ..checks.code_check import check_snippet
from ..checks.integrity import check_topic
from ..config import get_settings
from ..llm.client import LLMError, call_tool, data_block
from ..llm.prompts import steps as P
from ..schemas import CodeCheck, CodeExample
from .cache import cache_key
from .runner import load_inputs, load_result

log = logging.getLogger(__name__)


def topic_context(analysis_id: int, jd_id: str) -> tuple[dict, dict, str]:
    inp = load_inputs(analysis_id)
    result = load_result(analysis_id)
    if result is None:
        raise LLMError("The analysis has not finished yet.")
    items = {i["id"]: i for i in result["jd"]["items"]}
    if jd_id not in items:
        raise KeyError(jd_id)
    key = cache_key(
        "topic", inp["jd_text"], inp["resume_text"], items[jd_id],
        result["rank"]["rankings"][jd_id], result["match"]["matches"][jd_id],
        [(i["id"], i["name"]) for i in result["jd"]["items"]],
    )
    return inp, result, key


def get_cached_topic(analysis_id: int, jd_id: str) -> dict | None:
    _, _, key = topic_context(analysis_id, jd_id)
    cached = db.get_step(key)
    return cached["output"] if cached else None


async def _check_and_repair(ex: CodeExample, data: str, analysis_id: int, jd_id: str) -> tuple[CodeExample, CodeCheck]:
    check = await check_snippet(ex.language, ex.code, ex.runnable)
    if check.status == "verified" or check.tool.startswith("skipped"):
        return ex, check
    try:
        fixed = await call_tool(
            P.FIX_TOOL, P.fix_snippet(ex.language, ex.code, check.tool, check.detail or ""),
            data=data, step="fix", effort=get_settings().effort("topic"),
            analysis_id=analysis_id, ref=jd_id, max_tokens=16000,
        )
    except LLMError as e:
        log.warning("Snippet repair failed for %s: %s", jd_id, e)
        return ex, check
    repaired = ex.model_copy(update={"code": fixed.code})
    recheck = await check_snippet(repaired.language, repaired.code, repaired.runnable)
    if recheck.status == "verified":
        return repaired, recheck
    return ex, check  # keep the original with its first failure; shown as "not verified"


async def generate_topic(analysis_id: int, jd_id: str) -> dict:
    inp, result, key = topic_context(analysis_id, jd_id)
    cached = db.get_step(key)
    if cached:
        return cached["output"]

    items = result["jd"]["items"]
    item = next(i for i in items if i["id"] == jd_id)
    cv_by_id = {c["id"]: c for c in result["resume"]["items"]}
    data = data_block(inp["jd_text"], inp["resume_text"], inp["jd_url"])
    raw = await call_tool(
        P.TOPIC_TOOL,
        P.topic(item, result["rank"]["rankings"][jd_id], result["match"]["matches"][jd_id], cv_by_id, items),
        data=data, step="topic", effort=get_settings().effort("topic"),
        cache=True, analysis_id=analysis_id, ref=jd_id,
    )
    if raw.jd_id != jd_id:
        raw = raw.model_copy(update={"jd_id": jd_id})
    topic, dropped = check_topic(raw, {i["id"] for i in items})
    if topic is None:
        raise LLMError(f"Topic {jd_id} could not be traced to the job posting.")

    examples, checks = [], []
    for ex in topic.code_examples:
        ex2, chk = await _check_and_repair(ex, data, analysis_id, jd_id)
        examples.append(ex2.model_dump())
        checks.append(chk.model_dump())
    output = {**topic.model_dump(), "code_examples": [{**e, "check": c} for e, c in zip(examples, checks)]}
    db.put_step(key, "topic", P.VERSION["topic"], get_settings().anthropic_model, output,
                [asdict(d) for d in dropped])
    return output

