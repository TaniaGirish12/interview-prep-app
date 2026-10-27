import asyncio
import json
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app import db
from app.api import flashcards as api
from app.api import plan as plan_api
from app.checks.srs import CardState, review
from app.pipeline import flashcards as fc
from app.pipeline import runner, topic_queue, topics
from tests import test_pipeline_mocked as T
from tests.test_pipeline_mocked import analysis_id  # noqa: F401  (shared fixture)

TODAY = date(2026, 10, 23)

CARDS = {"cards": [
    {"kind": "concept", "front": "What does a mutex guarantee?", "back": "Mutual exclusion …", "label": "prediction",
     "jd_ids": ["JD-T02"]},
    {"kind": "question", "front": "How do you avoid deadlock?", "back": "Lock ordering …", "label": "prediction",
     "jd_ids": ["JD-T02", "JD-R02"]},
    {"kind": "mistake", "front": "Holding a lock during I/O?", "back": "Blocks other threads …", "label": "prediction",
     "jd_ids": ["JD-T02"]},
    {"kind": "code", "front": "What does std::lock_guard do?", "back": "RAII lock …", "label": "prediction",
     "jd_ids": ["JD-T99"]},  # unknown id → dropped
]}


# --- SM-2 -----------------------------------------------------------------------

def test_good_progression_and_again_reset():
    s, due = review(CardState(), "good", TODAY)
    assert (s.reps, s.interval_days, due) == (1, 1, TODAY + timedelta(days=1))
    s, due = review(s, "good", TODAY)
    assert s.interval_days == 3
    s, due = review(s, "good", TODAY)
    assert s.interval_days == round(3 * 2.5) == 8
    s, due = review(s, "again", TODAY)
    assert (s.reps, s.lapses, s.interval_days, due, s.ease) == (0, 1, 0, TODAY, 2.3)


def test_hard_and_easy_adjust_ease():
    hard, _ = review(CardState(), "hard", TODAY)
    easy, due = review(CardState(), "easy", TODAY)
    assert (hard.interval_days, hard.ease) == (1, 2.35)
    assert (easy.interval_days, easy.ease, due) == (3, 2.65, TODAY + timedelta(days=3))
    floor, _ = review(CardState(ease=1.35), "again", TODAY)
    assert floor.ease == 1.3


def test_due_is_capped_before_the_interview():
    s = CardState(ease=2.5, interval_days=20, reps=4)
    _, due = review(s, "easy", TODAY, interview=TODAY + timedelta(days=5))
    assert due == TODAY + timedelta(days=4)


# --- generation, review, boosts --------------------------------------------------

@pytest.fixture
async def analysis_with_topic(fake_llm, analysis_id, monkeypatch):
    monkeypatch.setattr(topic_queue.queue, "enqueue_prefetch", lambda _id: None)
    fake_llm({
        "extract_job_posting": [T.JD_RESPONSE], "rank_requirements": [T.RANK_RESPONSE],
        "extract_resume": [T.RESUME_RESPONSE], "match_requirements": [T.MATCH_RESPONSE],
        "write_topic_notes": [T.TOPIC_RESPONSE], "fix_snippet": [{"code": "def f(x):\n    pass\n"}],
    })
    await runner.run_analysis(analysis_id)
    return analysis_id


async def _wait(aid, jd_id):
    for _ in range(100):
        state = fc.status(aid, jd_id)
        if state["status"] != "generating":
            return state
        await asyncio.sleep(0.01)
    raise AssertionError("still generating")


async def test_cards_only_after_notes_and_only_once(fake_llm, analysis_with_topic):
    aid = analysis_with_topic
    assert fc.status(aid, "JD-T02")["status"] == "none"
    with pytest.raises(HTTPException) as e:  # no notes yet → nothing is generated
        await api.make_flashcards(aid, "JD-T02")
    assert e.value.status_code == 409

    await topics.generate_topic(aid, "JD-T02")
    client = fake_llm({"write_flashcards": [CARDS]})
    assert (await api.make_flashcards(aid, "JD-T02"))["status"] == "generating"
    assert (await _wait(aid, "JD-T02")) == {"status": "ready", "count": 3}
    assert (await api.make_flashcards(aid, "JD-T02"))["status"] == "ready"  # no second call
    assert len(client.calls) == 1
    assert "<topic_notes>" in client.calls[0]["messages"][0]["content"]

    deck = api.all_flashcards(aid)
    assert deck["stats"] == {"total": 3, "new": 3, "due": 0, "learned": 0, "next_due": None}
    assert deck["topics"][0]["jd_id"] == "JD-T02"
    assert deck["cards"][1]["jd_ids"] == ["JD-T02", "JD-R02"]


async def test_failed_generation_reports_and_can_retry(fake_llm, analysis_with_topic):
    aid = analysis_with_topic
    await topics.generate_topic(aid, "JD-T02")
    fake_llm({"write_flashcards": [{"cards": [{**CARDS["cards"][3]}] * 4}] * 2})  # every card untraceable
    await api.make_flashcards(aid, "JD-T02")
    state = await _wait(aid, "JD-T02")
    assert state["status"] == "error" and "traced" in state["error"]


async def test_review_updates_state_and_boosts_study_next(fake_llm, analysis_with_topic):
    aid = analysis_with_topic
    await topics.generate_topic(aid, "JD-T02")
    fake_llm({"write_flashcards": [CARDS]})
    await api.make_flashcards(aid, "JD-T02")
    await _wait(aid, "JD-T02")
    ids = [c["id"] for c in api.all_flashcards(aid)["cards"]]
    db.execute("UPDATE analyses SET interview_date = ?, hours_per_day = 2 WHERE id = ?",
               ((date.today() + timedelta(days=6)).isoformat(), aid))

    card = api.review_card(aid, ids[0], api.Review(grade="good"))
    assert card["reps"] == 1 and card["due"] == (date.today() + timedelta(days=1)).isoformat() and not card["is_due"]
    again = api.review_card(aid, ids[1], api.Review(grade="again"))
    assert again["is_due"] and again["lapses"] == 1
    api.review_card(aid, ids[2], api.Review(grade="hard"))
    with pytest.raises(HTTPException):
        api.review_card(aid, 999, api.Review(grade="good"))

    # 2 of 3 recent answers were Again/Hard → priority × (1 + 0.5 · 2/3).
    assert fc.weak_boosts(aid) == {"JD-T02": round(1 + 0.5 * 2 / 3, 3)}
    plan = plan_api.get_plan(aid)
    today = date.today().isoformat()
    assert plan["cards_due"][today] == 1  # the Again card
    assert sum(plan["cards_due"].values()) == 3
    stats = api.all_flashcards(aid)["stats"]
    assert stats["due"] == 1 and stats["learned"] == 2

    (T.CONTRACT_DIR / "flashcards.json").write_text(json.dumps(api.all_flashcards(aid), indent=1))
    (T.CONTRACT_DIR / "plan.json").write_text(json.dumps(plan, indent=1))
