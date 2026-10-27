from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..checks.srs import Grade
from ..llm.client import LLMError
from ..pipeline import flashcards as fc
from ..pipeline import runner

router = APIRouter(prefix="/api/analyses/{analysis_id}")


def _interview(analysis_id: int) -> date | None:
    row = db.one("SELECT interview_date FROM analyses WHERE id = ?", (analysis_id,))
    if row is None:
        raise HTTPException(404, "Analysis not found.")
    return date.fromisoformat(row["interview_date"]) if row["interview_date"] else None


@router.get("/topics/{jd_id}/flashcards")
async def topic_flashcards(analysis_id: int, jd_id: str) -> dict:
    try:
        return fc.status(analysis_id, jd_id)
    except KeyError as e:
        raise HTTPException(404, f"Unknown requirement {jd_id}.") from e
    except LLMError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/topics/{jd_id}/flashcards")
async def make_flashcards(analysis_id: int, jd_id: str) -> dict:
    """Only runs when the user clicks Make flashcards on a topic."""
    try:
        return fc.start(analysis_id, jd_id)
    except KeyError as e:
        raise HTTPException(404, f"Unknown requirement {jd_id}.") from e
    except LLMError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/flashcards")
def all_flashcards(analysis_id: int) -> dict:
    _interview(analysis_id)
    result = runner.load_result(analysis_id)
    if result is None:
        raise HTTPException(409, "The analysis has not finished yet.")
    today = date.today()
    cards = fc.list_cards(analysis_id, today)
    names = {i["id"]: i["name"] for i in result["jd"]["items"]}
    tiers = {k: v["tier"] for k, v in result["rank"]["rankings"].items()}
    topics: dict[str, dict] = {}
    for c in cards:
        t = topics.setdefault(c["jd_id"], {"jd_id": c["jd_id"], "name": names.get(c["jd_id"], c["jd_id"]),
                                           "tier": tiers.get(c["jd_id"]), "total": 0, "due": 0, "new": 0})
        t["total"] += 1
        t["due"] += c["is_due"] and not c["is_new"]
        t["new"] += c["is_new"]
    future = sorted(c["due"] for c in cards if not c["is_due"])
    return {
        "today": today.isoformat(),
        "cards": cards,
        "topics": sorted(topics.values(), key=lambda t: (t["tier"] or 9, t["jd_id"])),
        "stats": {
            "total": len(cards),
            "new": sum(c["is_new"] for c in cards),
            "due": sum(c["is_due"] and not c["is_new"] for c in cards),
            "learned": sum(c["reps"] > 0 and not c["is_due"] for c in cards),
            "next_due": future[0] if future else None,
        },
    }


class Review(BaseModel):
    grade: Grade


@router.post("/flashcards/{card_id}/review")
def review_card(analysis_id: int, card_id: int, body: Review) -> dict:
    interview = _interview(analysis_id)
    try:
        return fc.grade_card(analysis_id, card_id, body.grade, date.today(), interview)
    except KeyError as e:
        raise HTTPException(404, "Card not found.") from e
