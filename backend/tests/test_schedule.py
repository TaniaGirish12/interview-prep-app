from datetime import date, datetime, time

import sqlite3

from app import db
from app.checks.schedule import study_budget

NOW = datetime(2026, 10, 23, 20, 0)  # Friday evening


def test_morning_interview_gets_no_review_slot():
    b = study_budget(date(2026, 10, 27), time(9, 30), 3, NOW)
    # Today, Sat, Sun, Mon = 4 study days before a Tuesday-morning interview.
    assert b == {"days_until": 4, "hours_until": 85.5, "past": False, "study_days": 4,
                 "review_hours": 0.0, "total_hours": 12.0}


def test_afternoon_interview_adds_capped_review():
    assert study_budget(date(2026, 10, 27), time(14, 0), 3, NOW)["review_hours"] == 2.0
    assert study_budget(date(2026, 10, 27), time(14, 0), 1.5, NOW)["total_hours"] == 7.5  # 4·1.5 + 1.5


def test_without_time_or_hours():
    b = study_budget(date(2026, 10, 27), None, None, NOW)
    assert b["hours_until"] is None and b["total_hours"] is None and b["study_days"] == 4


def test_interview_today_and_past():
    today_later = study_budget(date(2026, 10, 23), time(21, 0), 2, NOW)
    assert today_later["study_days"] == 0 and not today_later["past"] and today_later["hours_until"] == 1.0
    assert study_budget(date(2026, 10, 23), time(9, 0), 2, NOW)["past"] is True
    assert study_budget(date(2026, 10, 1), None, 2, NOW) | {"days_until": 0} == {
        "days_until": 0, "hours_until": None, "past": True, "study_days": 0, "review_hours": 0.0, "total_hours": 0.0}


def test_old_database_gets_interview_time_column(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE analyses (id INTEGER PRIMARY KEY, resume_id INTEGER NOT NULL, jd_id INTEGER NOT NULL,"
                 " resume_hash TEXT NOT NULL, jd_hash TEXT NOT NULL, model TEXT NOT NULL, interview_date TEXT,"
                 " hours_per_day REAL, status TEXT NOT NULL DEFAULT 'pending', error TEXT, result_json TEXT,"
                 " created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (resume_hash, jd_hash, model))")
    conn.commit()
    conn.close()
    db.connect(path)
    cols = {r["name"] for r in db.all_rows("PRAGMA table_info(analyses)")}
    assert "interview_time" in cols
