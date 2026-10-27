"""SQLite storage. One local file, no accounts. Calls are short, so a single
connection guarded by a lock is enough for this single-user app."""

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY, filename TEXT, extractor TEXT, page_count INTEGER,
    text TEXT NOT NULL, text_hash TEXT NOT NULL, edited INTEGER DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY, url TEXT, source TEXT NOT NULL, title TEXT, company TEXT,
    meta_json TEXT, text TEXT NOT NULL, text_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY, resume_id INTEGER NOT NULL, jd_id INTEGER NOT NULL,
    resume_hash TEXT NOT NULL, jd_hash TEXT NOT NULL, model TEXT NOT NULL,
    interview_date TEXT, interview_time TEXT, hours_per_day REAL,
    status TEXT NOT NULL DEFAULT 'pending', error TEXT, result_json TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (resume_hash, jd_hash, model)
);
CREATE TABLE IF NOT EXISTS step_results (
    cache_key TEXT PRIMARY KEY, step TEXT NOT NULL, prompt_version INTEGER NOT NULL,
    model TEXT NOT NULL, output_json TEXT NOT NULL, dropped_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY, analysis_id INTEGER, step TEXT NOT NULL, ref TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
    cost_usd REAL, ok INTEGER, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS llm_calls_analysis ON llm_calls (analysis_id);
CREATE TABLE IF NOT EXISTS plan_log (
    id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL, jd_id TEXT, kind TEXT NOT NULL,
    hours REAL NOT NULL, done_on TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS plan_log_analysis ON plan_log (analysis_id);
CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL, jd_id TEXT NOT NULL, kind TEXT NOT NULL,
    front TEXT NOT NULL, back TEXT NOT NULL, label TEXT NOT NULL, jd_ids_json TEXT NOT NULL,
    ease REAL NOT NULL DEFAULT 2.5, interval_days INTEGER NOT NULL DEFAULT 0, reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0, due TEXT, last_grade TEXT, last_reviewed TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flashcards_analysis ON flashcards (analysis_id, jd_id);
CREATE TABLE IF NOT EXISTS flashcard_reviews (
    id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL, analysis_id INTEGER NOT NULL, jd_id TEXT NOT NULL,
    grade TEXT NOT NULL, reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flashcard_reviews_analysis ON flashcard_reviews (analysis_id, jd_id);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def connect(path: Path | None = None) -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None or path is not None:
            path = path or get_settings().db_path
            if str(path) != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            _migrate(_conn)
        return _conn


# Columns added after the first release; existing databases get them on startup.
_ADDED_COLUMNS = {"analyses": {"interview_time": "TEXT"}}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    conn.commit()


def execute(sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
    with _lock:
        conn = connect()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def one(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    with _lock:
        row = connect().execute(sql, params).fetchone()
        return dict(row) if row else None


def all_rows(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in connect().execute(sql, params).fetchall()]


# --- step cache ---------------------------------------------------------------

def get_step(cache_key: str) -> dict[str, Any] | None:
    row = one("SELECT output_json, dropped_json FROM step_results WHERE cache_key = ?", (cache_key,))
    if not row:
        return None
    return {"output": json.loads(row["output_json"]), "dropped": json.loads(row["dropped_json"])}


def put_step(cache_key: str, step: str, prompt_version: int, model: str, output: Any, dropped: list) -> None:
    execute(
        "INSERT OR REPLACE INTO step_results VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cache_key, step, prompt_version, model, json.dumps(output), json.dumps(dropped), now()),
    )


# --- usage --------------------------------------------------------------------

def log_call(analysis_id: int | None, step: str, ref: str | None, usage: dict[str, int], cost: float, ok: bool) -> None:
    execute(
        "INSERT INTO llm_calls (analysis_id, step, ref, input_tokens, output_tokens, cache_read_tokens,"
        " cache_write_tokens, cost_usd, ok, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (analysis_id, step, ref, usage["input"], usage["output"], usage["cache_read"],
         usage["cache_write"], cost, int(ok), now()),
    )


def analysis_cost(analysis_id: int) -> dict[str, Any]:
    row = one(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS usd,"
        " COALESCE(SUM(input_tokens), 0) AS input, COALESCE(SUM(output_tokens), 0) AS output,"
        " COALESCE(SUM(cache_read_tokens), 0) AS cache_read, COALESCE(SUM(cache_write_tokens), 0) AS cache_write"
        " FROM llm_calls WHERE analysis_id = ?",
        (analysis_id,),
    )
    assert row is not None
    row["usd"] = round(row["usd"], 4)
    return row
