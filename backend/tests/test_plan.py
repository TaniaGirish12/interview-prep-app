from datetime import date, datetime, time

from app.checks.plan import build_plan, build_tasks
from app.checks.schedule import study_budget

TODAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 9, 0)


def row(jd_id, tier, status, priority=1.0):
    return {"jd_id": jd_id, "name": jd_id, "tier": tier, "status": status, "confidence": 0.8, "priority": priority}


STUDY_NEXT = [row("JD-R01", 1, "gap"), row("JD-R02", 2, "partial"), row("JD-T01", 1, "strong", 0)]


def plan(days_ahead=5, hours=3.0, when=time(9, 0), study_next=STUDY_NEXT, gap_plans=None, done=None, done_today=0):
    interview = date(2026, 10, 23 + days_ahead)
    return build_plan(
        today=TODAY, budget=study_budget(interview, when, hours, NOW), interview_date=interview,
        hours_per_day=hours, study_next=study_next, gap_plans=gap_plans or {}, done_units=done or {},
        done_today_units=done_today,
    )


def blocks(p):
    return [(d["date"][-2:], b["jd_id"], b["kind"], b["hours"]) for d in p["days"] for b in d["blocks"]]


def test_default_estimates_by_status_and_tier():
    tasks = build_tasks(STUDY_NEXT, {}, {})
    # gap tier 1: 4 h → 2.5 learn + 1.5 practise; partial tier 2: 1.5 h → 1 + 0.5; strong tier 1: 1 h review last.
    assert [(t.jd_id, t.kind, t.units / 2) for t in tasks] == [
        ("JD-R01", "learn", 2.5), ("JD-R01", "practise", 1.5),
        ("JD-R02", "learn", 1.0), ("JD-R02", "practise", 0.5),
        ("JD-T01", "review", 1.0),
    ]


def test_fills_days_in_priority_order_with_reviews_and_final_review():
    p = plan()
    assert p["missing"] == [] and p["unscheduled"] == []
    assert [d["date"] for d in p["days"]] == ["2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"]
    b = blocks(p)
    # Day 1 (3 h): R01 learn 2.5 + R01 practise 0.5 (split); day 2: rest of practise, R02, strong review…
    assert b[:2] == [("23", "JD-R01", "learn", 2.5), ("23", "JD-R01", "practise", 0.5)]
    assert ("24", "JD-R01", "practise", 1.0) in b
    # Spaced reviews two or more days after learning, and the final review on the last study day.
    assert ("25", "JD-R01", "review", 0.5) in b
    assert any(k == "final" and d == "27" for d, _, k, _ in b)
    assert p["available_hours"] == 15.0 and p["needed_hours"] == 6.5
    for day in p["days"]:
        assert day["used_hours"] <= day["capacity_hours"]


def test_overflow_is_listed_not_dropped():
    many = [row(f"JD-R{i:02d}", 1, "gap") for i in range(1, 6)]  # 5 × 4 h = 20 h
    p = plan(days_ahead=2, hours=2.0, study_next=many)
    assert p["available_hours"] == 4.0 and p["scheduled_hours"] == 4.0
    left = {u["jd_id"]: u["hours"] for u in p["unscheduled"]}
    assert sum(left.values()) == 16.0 and "JD-R05" in left


def test_gap_plan_steps_replace_default_estimates():
    steps = {"JD-R01": [{"order": 2, "what": "Build a thread pool", "est_hours": 2},
                        {"order": 1, "what": "Read about mutexes", "est_hours": 1}]}
    tasks = build_tasks([row("JD-R01", 1, "gap")], steps, {})
    assert [(t.kind, t.units / 2, t.label) for t in tasks] == [
        ("learn", 1.0, "Learn: Read about mutexes"), ("learn", 2.0, "Learn: Build a thread pool"),
        ("practise", 2.0, tasks[2].label),
    ]


def test_done_hours_are_subtracted_and_reduce_today():
    tasks = build_tasks([row("JD-R01", 1, "gap")], {}, {("JD-R01", "learn"): 3})  # 1.5 h of 2.5 learnt
    assert [(t.kind, t.units / 2) for t in tasks] == [("learn", 1.0), ("practise", 1.5)]
    p = plan(done_today=4)  # 2 h already done today
    assert p["days"][0]["capacity_hours"] == 1.0


def test_afternoon_interview_gets_morning_warmup():
    p = plan(days_ahead=2, when=time(15, 0))
    last = p["days"][-1]
    assert last["interview_day"] and last["date"] == "2026-10-25"
    assert [b["kind"] for b in last["blocks"]] == ["final"] and last["capacity_hours"] == 2.0


def test_missing_inputs_and_past_interview():
    p = build_plan(today=TODAY, budget=None, interview_date=None, hours_per_day=None, study_next=STUDY_NEXT,
                   gap_plans={}, done_units={}, done_today_units=0)
    assert p["missing"] == ["interview_date", "hours_per_day"] and p["days"] == []
    assert p["needed_hours"] == 6.5 and len(p["unscheduled"]) == 3
    past = plan(days_ahead=-1)
    assert past["past"] and past["days"] == []
