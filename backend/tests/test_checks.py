import shutil

import pytest

from app.checks import code_check
from app.checks.integrity import check_coverage, check_topic
from app.checks.normalize import contains, normalize
from app.checks.quotes import verify_match_evidence, verify_quotes
from app.checks.scoring import compute_scores, priority, weighted_score
from app.schemas import JDItem, JDItemLLM, Match, MatchLLM, RankedRequirement, TopicContentLLM

SOURCE = "Concurrency awareness – You understand threads,\nsynchronisation primitives (“mutexes”) and ﬁles."


@pytest.mark.parametrize("quote", [
    "Concurrency awareness - You understand threads, synchronisation primitives",  # en dash → hyphen, line break
    'primitives ("mutexes")',                                                   # curly → straight quotes
    "and files.",                                                               # ﬁ ligature
    "CONCURRENCY AWARENESS",                                                    # case
])
def test_quote_normalisation_matches(quote):
    assert contains(normalize(SOURCE), quote)


@pytest.mark.parametrize("quote", ["Concurrency … threads", "You master threads", "", "  "])
def test_quote_normalisation_rejects(quote):
    assert not contains(normalize(SOURCE), quote)


def _jd(quote: str, **kw) -> JDItemLLM:
    return JDItemLLM(category="requirement", kind="skill", name="x", quote=quote, section="Profile", **kw)


def test_verify_quotes_drops_unfound():
    res = verify_quotes([_jd("You understand threads"), _jd("Expert knowledge of Rust")], SOURCE, "jd")
    assert [i.quote for i in res.kept] == ["You understand threads"]
    assert res.dropped[0].reason == "quote not found in source"


def test_evidence_check_downgrades_when_all_evidence_fails():
    resume = "- Implemented a thread-safe queue in C++17.\nLanguages: C++, Python"
    cv = {"CV-01": "Implemented a thread-safe queue in C++17.", "CV-02": "Languages: C++, Python"}
    matches = [
        MatchLLM(jd_id="JD-R01", status="strong", confidence=0.9, rationale="r",
                 evidence=[{"cv_id": "CV-01", "quote": "thread-safe queue in C++17"}]),
        MatchLLM(jd_id="JD-R02", status="partial", confidence=0.6, rationale="r",
                 evidence=[{"cv_id": "CV-02", "quote": "thread-safe queue"}]),        # wrong CV id
        MatchLLM(jd_id="JD-R03", status="partial", confidence=0.6, rationale="r",
                 evidence=[{"cv_id": "CV-09", "quote": "Languages: C++"}]),           # unknown CV id
    ]
    out, dropped = verify_match_evidence(matches, resume, cv)
    assert out[0].status == "strong" and not out[0].downgraded
    assert out[1].status == "gap" and out[1].downgraded and out[1].evidence == []
    assert out[2].status == "gap" and out[2].downgraded
    assert {d.reason for d in dropped} == {"evidence quote is not part of CV-02", "unknown CV id CV-09"}


def test_coverage_drops_unknown_and_duplicates():
    rows = [RankedRequirement(jd_id="JD-R01", tier=1, reason="r", skill_area="a"),
            RankedRequirement(jd_id="JD-R01", tier=2, reason="dup", skill_area="a"),
            RankedRequirement(jd_id="JD-R09", tier=1, reason="r", skill_area="a")]
    by_id, missing, dropped = check_coverage(rows, ["JD-R01", "JD-R02"], "rank")
    assert by_id["JD-R01"].tier == 1
    assert missing == ["JD-R02"]
    assert len(dropped) == 2


def _topic(**over) -> TopicContentLLM:
    base = {
        "jd_id": "JD-R01", "title": "t",
        "explanation": [{"level": lvl, "heading": "h", "body_md": "b"}
                        for lvl in ("fundamentals", "intermediate", "interview")],
        "diagram": None,
        "code_examples": [{"language": "python", "title": "t", "code": "print(1)", "runnable": True,
                           "explanation": "e", "jd_ids": ["JD-R01", "JD-R77"]},
                          {"language": "python", "title": "t", "code": "print(2)", "runnable": True,
                           "explanation": "e", "jd_ids": ["JD-R77"]}],
        "common_mistakes": [{"text": "m", "label": "fact", "jd_ids": ["JD-R01"]}],
        "real_world_use": [{"text": "u", "label": "prediction", "jd_ids": ["JD-T99"]}],
        "likely_questions": [{"question": "q", "model_answer": "a", "difficulty": "core",
                              "label": "prediction", "jd_ids": ["JD-R01"]}] * 3,
    }
    base.update(over)
    return TopicContentLLM.model_validate(base)


def test_topic_integrity_strips_unknown_ids():
    cleaned, dropped = check_topic(_topic(), {"JD-R01", "JD-T01"})
    assert cleaned is not None
    assert [e.jd_ids for e in cleaned.code_examples] == [["JD-R01"]]
    assert cleaned.real_world_use == []
    assert len(dropped) == 2


def test_topic_with_unknown_jd_id_is_dropped():
    cleaned, dropped = check_topic(_topic(jd_id="JD-R50"), {"JD-R01"})
    assert cleaned is None and dropped


def test_scoring_by_hand():
    items = [JDItem(id=i, category="requirement", kind="skill", name=i, quote="quote", section="s")
             for i in ("JD-R01", "JD-R02", "JD-R03", "JD-R04")]
    rankings = {
        "JD-R01": RankedRequirement(jd_id="JD-R01", tier=1, reason="r", skill_area="A"),
        "JD-R02": RankedRequirement(jd_id="JD-R02", tier=2, reason="r", skill_area="A"),
        "JD-R03": RankedRequirement(jd_id="JD-R03", tier=3, reason="r", skill_area="B"),
        "JD-R04": RankedRequirement(jd_id="JD-R04", tier=4, reason="r", skill_area="B"),
    }
    m = lambda i, s, c: Match(jd_id=i, status=s, evidence=[], rationale="r", confidence=c)  # noqa: E731
    matches = {"JD-R01": m("JD-R01", "strong", 1.0), "JD-R02": m("JD-R02", "partial", 0.5),
               "JD-R03": m("JD-R03", "gap", 1.0), "JD-R04": m("JD-R04", "gap", 0.0)}
    s = compute_scores(items, rankings, matches, ["A", "B"])
    # (4·1 + 3·0.5 + 2·0 + 1·0) / (4+3+2+1) = 5.5 / 10
    assert s["match_score"] == 55.0
    assert {r["area"]: r["score"] for r in s["radar"]} == {"A": round(100 * 5.5 / 7, 1), "B": 0.0}
    # priorities: R01 0; R02 3·0.5·1.25 = 1.875; R03 2·1·1 = 2; R04 1·1·1.5 = 1.5
    assert [r["jd_id"] for r in s["study_next"]] == ["JD-R03", "JD-R02", "JD-R04", "JD-R01"]
    assert s["tier_status"][0] == {"tier": 1, "strong": 1, "partial": 0, "gap": 0}


def test_priority_and_empty_score():
    assert priority(1, "gap", 1.0) == 4.0
    assert priority(1, "strong", 0.2) == 0.0
    assert weighted_score([]) is None


GOOD_CPP = """#include <iostream>
#include <mutex>
#include <thread>
int main() {
    int counter = 0;
    std::mutex m;
    auto work = [&] { for (int i = 0; i < 1000; ++i) { std::lock_guard<std::mutex> g(m); ++counter; } };
    std::thread a(work), b(work);
    a.join(); b.join();
    std::cout << counter << "\\n";
    return 0;
}
"""
RACY_CPP = GOOD_CPP.replace("std::lock_guard<std::mutex> g(m); ", "")
needs_gxx = pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not installed")


@needs_gxx
async def test_cpp_good_snippet_runs_clean_under_tsan():
    chk = await code_check.check_cpp(GOOD_CPP, runnable=True)
    assert chk.status == "verified", chk.detail


@needs_gxx
async def test_cpp_data_race_is_caught():
    chk = await code_check.check_cpp(RACY_CPP, runnable=True)
    assert chk.status == "not_verified"
    assert "ThreadSanitizer" in (chk.detail or "")


@needs_gxx
async def test_cpp_compile_error_and_warning():
    assert (await code_check.check_cpp("int main() { return x; }", False)).status == "not_verified"
    warn = await code_check.check_cpp("int main() { int unused = 1; return 0; }", False)
    assert warn.status == "not_verified" and "unused" in warn.detail


async def test_cpp_without_gxx(monkeypatch):
    monkeypatch.setattr(code_check, "gxx_path", lambda: None)
    chk = await code_check.check_cpp(GOOD_CPP, runnable=True)
    assert chk.status == "not_verified" and chk.tool.startswith("skipped")


async def test_python_checks():
    assert (await code_check.check_python("def f(x: int) -> int:\n    return x\n")).status == "verified"
    assert (await code_check.check_python("def f(:\n")).status == "not_verified"
    # except* is Python 3.11+, so it must fail the 3.10 grammar check even on a newer interpreter.
    newer = "try:\n    pass\nexcept* ValueError:\n    pass\n"
    chk = await code_check.check_python(newer)
    assert chk.status == "not_verified" and "3.10" in chk.detail
