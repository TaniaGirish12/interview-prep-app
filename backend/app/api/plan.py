from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import db
from ..checks.plan import UNIT, build_plan
from ..checks.schedule import study_budget
from ..checks.scoring import compute_scores
from ..pipeline import flashcards, gaps, runner
from ..schemas import JDItem, Match, RankedRequirement, JdId

router = APIRouter(prefix="/api/analyses/{analysis_id}/plan")


def _analysis(analysis_id: int) -> tuple[dict, dict]:
    row = db.one("SELECT interview_date, interview_time, hours_per_day FROM analyses WHERE id = ?", (analysis_id,))
    if row is None:
        raise HTTPException(404, "Analysis not found.")
    result = runner.load_result(analysis_id)
    if result is None:
        raise HTTPException(409, "The analysis has not finished yet.")
    return row, result


@router.get("")
def get_plan(analysis_id: int) -> dict:
    row, result = _analysis(analysis_id)
    now = datetime.now()
    today = now.date()
    interview_date = date.fromisoformat(row["interview_date"]) if row["interview_date"] else None
    interview_time = time.fromisoformat(row["interview_time"]) if row["interview_time"] else None
    budget = study_budget(interview_date, interview_time, row["hours_per_day"], now) if interview_date else None

    scores = compute_scores(
        [JDItem(**i) for i in result["jd"]["items"]],
        {k: RankedRequirement(**v) for k, v in result["rank"]["rankings"].items()},
        {k: Match(**v) for k, v in result["match"]["matches"].items()},
        result["rank"]["skill_areas"],
        boosts=flashcards.weak_boosts(analysis_id),
    )
    # Use the gap plan's steps and estimates only if it was already generated; never start it here.
    try:
        gap_state = gaps.get_gaps(analysis_id)
    except ValueError:
        gap_state = {"status": "not_started"}
    gap_plans = {p["jd_id"]: p["steps"] for p in gap_state.get("plans", [])} if gap_state["status"] == "ready" else {}

    log = db.all_rows("SELECT * FROM plan_log WHERE analysis_id = ? ORDER BY id", (analysis_id,))
    done_units: dict[tuple[str, str], int] = {}
    for entry in log:
        if entry["jd_id"]:
            key = (entry["jd_id"], entry["kind"])
            done_units[key] = done_units.get(key, 0) + round(entry["hours"] / UNIT)
    today_log = [e for e in log if e["done_on"] == today.isoformat()]

    plan = build_plan(
        today=today, budget=budget, interview_date=interview_date, hours_per_day=row["hours_per_day"],
        study_next=scores["study_next"], gap_plans=gap_plans, done_units=done_units,
        done_today_units=sum(round(e["hours"] / UNIT) for e in today_log),
    )
    names = {i["id"]: i["name"] for i in result["jd"]["items"]}
    return {
        **plan,
        "today": today.isoformat(),
        "budget": budget,
        "uses_gap_plan": bool(gap_plans),
        "done_today": [{**e, "name": names.get(e["jd_id"], "Tier 1 topics")} for e in today_log],
        "done_hours_total": sum(e["hours"] for e in log),
        "cards_due": flashcards.due_counts(analysis_id, today),
    }


class DoneEntry(BaseModel):
    jd_id: JdId | None = None
    kind: Literal["learn", "practise", "review", "final"]
    hours: float = Field(gt=0, le=12)

    @field_validator("hours")
    @classmethod
    def half_hours(cls, v: float) -> float:
        if round(v / UNIT) * UNIT != v:
            raise ValueError("hours must be a multiple of 0.5")
        return v


@router.post("/done")
def mark_done(analysis_id: int, body: DoneEntry) -> dict:
    _, result = _analysis(analysis_id)
    if body.jd_id and body.jd_id not in {i["id"] for i in result["jd"]["items"]}:
        raise HTTPException(404, f"Unknown requirement {body.jd_id}.")
    cur = db.execute(
        "INSERT INTO plan_log (analysis_id, jd_id, kind, hours, done_on, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (analysis_id, body.jd_id, body.kind, body.hours, date.today().isoformat(), db.now()),
    )
    return {"id": cur.lastrowid}


@router.delete("/done/{entry_id}")
def undo_done(analysis_id: int, entry_id: int) -> dict:
    cur = db.execute("DELETE FROM plan_log WHERE id = ? AND analysis_id = ?", (entry_id, analysis_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "Entry not found.")
    return {"deleted": entry_id}
