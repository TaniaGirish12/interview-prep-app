import asyncio
import json
from datetime import date, datetime, time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import db
from ..checks.code_check import gxx_path
from ..checks.schedule import study_budget
from ..checks.scoring import compute_scores
from ..config import get_settings
from ..pipeline import events, flashcards, gaps, runner
from ..pipeline.topic_queue import queue
from ..schemas import JDItem, Match, RankedRequirement

router = APIRouter(prefix="/api")


def _hhmm(t: time | None) -> str | None:
    return t.isoformat(timespec="minutes") if t else None


class NewAnalysis(BaseModel):
    resume_id: int
    jd_id: int
    interview_date: date | None = None
    interview_time: time | None = None
    hours_per_day: float | None = Field(default=None, gt=0, le=16)


@router.post("/analyses")
async def create_analysis(body: NewAnalysis) -> dict:
    resume = db.one("SELECT text_hash FROM resumes WHERE id = ?", (body.resume_id,))
    jd = db.one("SELECT text_hash FROM job_postings WHERE id = ?", (body.jd_id,))
    if not resume or not jd:
        raise HTTPException(404, "Resume or job posting not found.")
    model = get_settings().anthropic_model
    when = body.interview_date.isoformat() if body.interview_date else None
    existing = db.one("SELECT id, status FROM analyses WHERE resume_hash = ? AND jd_hash = ? AND model = ?",
                      (resume["text_hash"], jd["text_hash"], model))
    if existing:
        db.execute("UPDATE analyses SET resume_id = ?, jd_id = ?, interview_date = ?, interview_time = ?,"
                   " hours_per_day = ?, updated_at = ? WHERE id = ?",
                   (body.resume_id, body.jd_id, when, _hhmm(body.interview_time), body.hours_per_day,
                    db.now(), existing["id"]))
        if existing["status"] != "done":
            runner.start(existing["id"])
        return {"analysis_id": existing["id"], "reused": True}
    cur = db.execute(
        "INSERT INTO analyses (resume_id, jd_id, resume_hash, jd_hash, model, interview_date, interview_time,"
        " hours_per_day, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
        (body.resume_id, body.jd_id, resume["text_hash"], jd["text_hash"], model, when,
         _hhmm(body.interview_time), body.hours_per_day, db.now(), db.now()),
    )
    runner.start(cur.lastrowid)
    return {"analysis_id": cur.lastrowid, "reused": False}


@router.get("/analyses")
def list_analyses() -> list[dict]:
    """Every interview being prepared, for the sidebar. Role, company and match score
    come from the finished analysis when there is one, else from the fetched page."""
    rows = db.all_rows(
        "SELECT a.id, a.status, a.created_at, a.interview_date, a.interview_time, a.hours_per_day, a.result_json,"
        " j.title, j.company, r.filename"
        " FROM analyses a JOIN job_postings j ON j.id = a.jd_id JOIN resumes r ON r.id = a.resume_id"
        " ORDER BY a.updated_at DESC LIMIT 200"
    )
    out = []
    for row in rows:
        raw = row.pop("result_json")
        result = json.loads(raw) if raw else None
        match_score = None
        if result:
            meta = result["jd"]["meta"]
            row["title"] = meta.get("role_title") or row["title"]
            row["company"] = meta.get("company_name") or row["company"]
            match_score = compute_scores(
                [JDItem(**i) for i in result["jd"]["items"]],
                {k: RankedRequirement(**v) for k, v in result["rank"]["rankings"].items()},
                {k: Match(**v) for k, v in result["match"]["matches"].items()},
                result["rank"]["skill_areas"],
            )["match_score"]
        if runner.is_running(row["id"]):
            row["status"] = "running"
        out.append({**row, "match_score": match_score})
    return out


class ScheduleUpdate(BaseModel):
    interview_date: date | None = None
    interview_time: time | None = None
    hours_per_day: float | None = Field(default=None, gt=0, le=16)


@router.patch("/analyses/{analysis_id}")
def update_schedule(analysis_id: int, body: ScheduleUpdate) -> dict:
    """Set or clear the interview date, time and hours per day. Only fields sent are changed."""
    _row(analysis_id)
    fields = body.model_fields_set & {"interview_date", "interview_time", "hours_per_day"}
    if fields:
        values = {"interview_date": body.interview_date.isoformat() if body.interview_date else None,
                  "interview_time": _hhmm(body.interview_time),
                  "hours_per_day": body.hours_per_day}
        sets = ", ".join(f"{f} = ?" for f in sorted(fields))
        db.execute(f"UPDATE analyses SET {sets} WHERE id = ?",
                   (*[values[f] for f in sorted(fields)], analysis_id))
    row = db.one("SELECT interview_date, interview_time, hours_per_day FROM analyses WHERE id = ?", (analysis_id,))
    return {"analysis_id": analysis_id, **row, "schedule": _schedule(row)}


def _schedule(row: dict) -> dict | None:
    if not row["interview_date"]:
        return None
    return study_budget(
        date.fromisoformat(row["interview_date"]),
        time.fromisoformat(row["interview_time"]) if row["interview_time"] else None,
        row["hours_per_day"],
        datetime.now(),
    )


def _row(analysis_id: int) -> dict:
    row = db.one(
        "SELECT a.*, j.url AS jd_url, j.title AS jd_title, j.company AS jd_company, j.source AS jd_source,"
        " r.filename AS resume_filename FROM analyses a JOIN job_postings j ON j.id = a.jd_id"
        " JOIN resumes r ON r.id = a.resume_id WHERE a.id = ?",
        (analysis_id,),
    )
    if not row:
        raise HTTPException(404, "Analysis not found.")
    return row


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: int) -> dict:
    row = _row(analysis_id)
    status = "running" if runner.is_running(analysis_id) else row["status"]
    out = {
        "id": analysis_id, "status": status, "error": row["error"],
        "interview_date": row["interview_date"], "interview_time": row["interview_time"],
        "hours_per_day": row["hours_per_day"], "schedule": _schedule(row),
        "created_at": row["created_at"], "model": row["model"],
        "jd": {"url": row["jd_url"], "title": row["jd_title"], "company": row["jd_company"],
               "source": row["jd_source"]},
        "resume": {"filename": row["resume_filename"]},
        "cost": db.analysis_cost(analysis_id),
        "backend": get_settings().llm_backend,
        "gxx_available": gxx_path() is not None,
        "result": None,
    }
    result = runner.load_result(analysis_id)
    if result is None or status != "done":
        if row["status"] in ("pending", "running") and not runner.is_running(analysis_id):
            runner.start(analysis_id)  # the server restarted mid-run
        return out
    inp = runner.load_inputs(analysis_id)
    items = [JDItem(**i) for i in result["jd"]["items"]]
    rankings = {k: RankedRequirement(**v) for k, v in result["rank"]["rankings"].items()}
    matches = {k: Match(**v) for k, v in result["match"]["matches"].items()}
    queue.enqueue_prefetch(analysis_id)  # resumes pre-generation after a restart
    out["result"] = {
        "meta": result["jd"]["meta"],
        "about_company": result["jd"]["about_company"],
        "jd_items": result["jd"]["items"],
        "skill_areas": result["rank"]["skill_areas"],
        "rankings": result["rank"]["rankings"],
        "cv_items": result["resume"]["items"],
        "matches": result["match"]["matches"],
        "defaulted": {"rank": result["rank"]["defaulted"], "match": result["match"]["defaulted"]},
        "dropped": runner.all_dropped(result, inp),
        "scores": compute_scores(items, rankings, matches, result["rank"]["skill_areas"],
                                 boosts=flashcards.weak_boosts(analysis_id)),
        "topics": {i.id: queue.status_of(analysis_id, i.id)["status"] for i in items},
    }
    return out


@router.post("/analyses/{analysis_id}/retry")
async def retry_analysis(analysis_id: int) -> dict:
    _row(analysis_id)
    runner.start(analysis_id)
    return {"analysis_id": analysis_id}


@router.get("/analyses/{analysis_id}/events")
async def analysis_events(analysis_id: int, request: Request) -> StreamingResponse:
    _row(analysis_id)

    async def stream():
        history, q = events.subscribe(analysis_id)
        try:
            for item in history:
                yield _sse(item)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(item)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            events.unsubscribe(analysis_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(item: dict) -> str:
    return f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"


@router.get("/analyses/{analysis_id}/gaps")
async def get_gaps(analysis_id: int) -> dict:
    _row(analysis_id)
    try:
        state = gaps.get_gaps(analysis_id)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    if state["status"] == "not_started":
        gaps.start_gaps(analysis_id)
        state = {"status": "generating"}
    return state


@router.post("/analyses/{analysis_id}/gaps/retry")
async def retry_gaps(analysis_id: int) -> dict:
    _row(analysis_id)
    gaps.start_gaps(analysis_id)
    return {"status": "generating"}
