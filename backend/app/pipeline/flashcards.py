"""Flashcards: generated on demand per topic (only when the user asks), stored with
their spaced-repetition state, and reviewed with Again / Hard / Good / Easy."""

import asyncio
import json
import logging
from datetime import date

from .. import db
from ..checks.srs import CardState, Grade, review
from ..config import get_settings
from ..llm.client import LLMError, call_tool, data_block
from ..llm.prompts import steps as P
from .cache import cache_key
from .topics import topic_context

log = logging.getLogger(__name__)

_tasks: dict[tuple[int, str], asyncio.Task] = {}
_errors: dict[tuple[int, str], str] = {}

WEAK_GRADES = ("again", "hard")
WEAK_WINDOW = 20      # last N reviews per requirement
WEAK_MIN_REVIEWS = 3  # fewer reviews than this say nothing yet
WEAK_BOOST = 0.5      # study-next priority × (1 + 0.5 · share of Again/Hard)


def _count(analysis_id: int, jd_id: str) -> int:
    row = db.one("SELECT COUNT(*) AS n FROM flashcards WHERE analysis_id = ? AND jd_id = ?", (analysis_id, jd_id))
    return row["n"] if row else 0


def status(analysis_id: int, jd_id: str) -> dict:
    topic_context(analysis_id, jd_id)  # raises KeyError for an unknown requirement
    n = _count(analysis_id, jd_id)
    if n:
        return {"status": "ready", "count": n}
    key = (analysis_id, jd_id)
    task = _tasks.get(key)
    if task and not task.done():
        return {"status": "generating", "count": 0}
    if key in _errors:
        return {"status": "error", "count": 0, "error": _errors[key]}
    return {"status": "none", "count": 0}


def start(analysis_id: int, jd_id: str) -> dict:
    """Generate cards for one topic. Requires the topic's notes; never runs twice."""
    _, _, topic_key = topic_context(analysis_id, jd_id)
    if db.get_step(topic_key) is None:
        raise LLMError("Open this topic's notes first; flashcards are made from them.")
    current = status(analysis_id, jd_id)
    if current["status"] in ("ready", "generating"):
        return current
    _errors.pop((analysis_id, jd_id), None)
    _tasks[(analysis_id, jd_id)] = asyncio.create_task(_generate(analysis_id, jd_id))
    return {"status": "generating", "count": 0}


async def _generate(analysis_id: int, jd_id: str) -> None:
    try:
        inp, result, topic_key = topic_context(analysis_id, jd_id)
        topic = db.get_step(topic_key)["output"]
        known = {i["id"] for i in result["jd"]["items"]}
        key = cache_key("cards", topic_key)
        cached = db.get_step(key)
        if cached:
            cards = cached["output"]["cards"]
        else:
            raw = await call_tool(
                P.CARDS_TOOL, P.flashcards(topic, result["jd"]["items"]),
                data=data_block(inp["jd_text"], inp["resume_text"], inp["jd_url"]),
                step="cards", effort=get_settings().effort("extract"), analysis_id=analysis_id, ref=jd_id,
                max_tokens=16000,
            )
            cards, dropped = [], []
            for c in raw.cards:
                ids = [i for i in c.jd_ids if i in known]
                if ids:
                    cards.append({**c.model_dump(), "jd_ids": ids})
                else:
                    dropped.append({"step": "cards", "reason": "cites no known JD id", "item": c.model_dump()})
            if not cards:
                raise LLMError("None of the generated cards could be traced to the job posting.")
            db.put_step(key, "cards", P.VERSION["cards"], get_settings().anthropic_model, {"cards": cards}, dropped)
        if _count(analysis_id, jd_id) == 0:  # idempotent: never insert a topic's cards twice
            for c in cards:
                db.execute(
                    "INSERT INTO flashcards (analysis_id, jd_id, kind, front, back, label, jd_ids_json, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (analysis_id, jd_id, c["kind"], c["front"], c["back"], c["label"], json.dumps(c["jd_ids"]), db.now()),
                )
    except Exception as e:  # reported on the topic page, which offers a retry
        log.exception("Flashcards failed for %s %s", analysis_id, jd_id)
        _errors[(analysis_id, jd_id)] = str(e)


def _card(row: dict, today: str) -> dict:
    return {
        "id": row["id"], "jd_id": row["jd_id"], "kind": row["kind"], "front": row["front"], "back": row["back"],
        "label": row["label"], "jd_ids": json.loads(row["jd_ids_json"]), "reps": row["reps"],
        "lapses": row["lapses"], "interval_days": row["interval_days"], "due": row["due"],
        "last_grade": row["last_grade"], "is_new": row["due"] is None,
        "is_due": row["due"] is None or row["due"] <= today,
    }


def list_cards(analysis_id: int, today: date) -> list[dict]:
    rows = db.all_rows("SELECT * FROM flashcards WHERE analysis_id = ? ORDER BY jd_id, id", (analysis_id,))
    return [_card(r, today.isoformat()) for r in rows]


def grade_card(analysis_id: int, card_id: int, grade: Grade, today: date, interview: date | None) -> dict:
    row = db.one("SELECT * FROM flashcards WHERE id = ? AND analysis_id = ?", (card_id, analysis_id))
    if row is None:
        raise KeyError(card_id)
    state, due = review(CardState(row["ease"], row["interval_days"], row["reps"], row["lapses"]), grade, today, interview)
    db.execute(
        "UPDATE flashcards SET ease = ?, interval_days = ?, reps = ?, lapses = ?, due = ?, last_grade = ?,"
        " last_reviewed = ? WHERE id = ?",
        (state.ease, state.interval_days, state.reps, state.lapses, due.isoformat(), grade, db.now(), card_id),
    )
    db.execute("INSERT INTO flashcard_reviews (card_id, analysis_id, jd_id, grade, reviewed_at) VALUES (?, ?, ?, ?, ?)",
               (card_id, analysis_id, row["jd_id"], grade, db.now()))
    return _card(db.one("SELECT * FROM flashcards WHERE id = ?", (card_id,)), today.isoformat())


def weak_boosts(analysis_id: int) -> dict[str, float]:
    """Study-next multiplier per requirement from recent Again/Hard answers."""
    rows = db.all_rows(
        "SELECT jd_id, grade FROM flashcard_reviews WHERE analysis_id = ? ORDER BY id DESC", (analysis_id,))
    recent: dict[str, list[str]] = {}
    for r in rows:
        bucket = recent.setdefault(r["jd_id"], [])
        if len(bucket) < WEAK_WINDOW:
            bucket.append(r["grade"])
    return {
        jd_id: round(1 + WEAK_BOOST * sum(g in WEAK_GRADES for g in grades) / len(grades), 3)
        for jd_id, grades in recent.items() if len(grades) >= WEAK_MIN_REVIEWS
    }


def due_counts(analysis_id: int, today: date) -> dict[str, int]:
    """Cards due per date; new and overdue cards count for today."""
    out: dict[str, int] = {}
    t = today.isoformat()
    for r in db.all_rows("SELECT due FROM flashcards WHERE analysis_id = ?", (analysis_id,)):
        day = t if r["due"] is None or r["due"] < t else r["due"]
        out[day] = out.get(day, 0) + 1
    return out
