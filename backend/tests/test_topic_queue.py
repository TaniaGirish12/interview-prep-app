import json

from app import db
from app.config import get_settings
from app.pipeline import topic_queue
from app.pipeline.topic_queue import TopicQueue


def _seed_result(n_tier12: int, n_tier3: int) -> int:
    items, rankings, matches = [], {}, {}
    for i in range(n_tier12 + n_tier3):
        jd_id = f"JD-R{i + 1:02d}"
        tier = 1 if i < n_tier12 else 3
        items.append({"id": jd_id, "category": "requirement", "kind": "skill", "name": jd_id,
                      "quote": "a quote", "section": "Profile"})
        rankings[jd_id] = {"jd_id": jd_id, "tier": tier, "reason": "r", "skill_area": "A"}
        matches[jd_id] = {"jd_id": jd_id, "status": "gap", "evidence": [], "rationale": "r",
                          "confidence": 0.5 + i / 100, "downgraded": False}
    result = {"jd": {"items": items}, "rank": {"skill_areas": ["A"], "rankings": rankings},
              "match": {"matches": matches}}
    return db.execute(
        "INSERT INTO analyses (resume_id, jd_id, resume_hash, jd_hash, model, status, result_json, created_at,"
        " updated_at) VALUES (1, 1, 'a', 'b', 'm', 'done', ?, ?, ?)",
        (json.dumps(result), db.now(), db.now()),
    ).lastrowid


async def test_prefetch_is_capped(monkeypatch):
    aid = _seed_result(n_tier12=8, n_tier3=4)
    cached = {"JD-R01"}
    monkeypatch.setattr(topic_queue, "get_cached_topic", lambda _a, jd: {"x": 1} if jd in cached else None)
    monkeypatch.setattr(get_settings(), "prefetch_topics", 3)
    q = TopicQueue()
    q.enqueue_prefetch(aid)
    # Top 3 tier 1–2 rows by study-next priority (lower confidence first): R01 (cached), R02, R03.
    assert sorted(jd for _, jd in q.pending) == ["JD-R02", "JD-R03"]
    q.enqueue_prefetch(aid)  # reopening the analysis does not pull in more topics
    assert len(q.pending) == 2


async def test_prefetch_off(monkeypatch):
    aid = _seed_result(n_tier12=4, n_tier3=0)
    monkeypatch.setattr(topic_queue, "get_cached_topic", lambda _a, _jd: None)
    monkeypatch.setattr(get_settings(), "prefetch_topics", 0)
    q = TopicQueue()
    q.enqueue_prefetch(aid)
    assert q.pending == {}
    assert q.open(aid, "JD-R04") == "queued"  # opening a topic still generates it
