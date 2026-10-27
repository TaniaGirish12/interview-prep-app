import pytest
from pydantic import ValidationError

from app.llm.prompts import steps as P
from app.llm.tool_schema import input_schema
from app.schemas import MatchLLM, RankingLLM, TopicContentLLM

ALL_TOOLS = [P.JD_TOOL, P.RANK_TOOL, P.RESUME_TOOL, P.MATCH_TOOL, P.TOPIC_TOOL, P.FIX_TOOL, P.GAPS_TOOL]


@pytest.mark.parametrize("spec", ALL_TOOLS, ids=lambda s: s.name)
def test_strict_tool_schema(spec):
    schema = input_schema(spec.model)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for key in ("minLength", "maxLength", "maximum", "minimum", "maxItems"):
                assert key not in node
            if "minItems" in node:
                assert node["minItems"] in (0, 1)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)


def test_ranking_rejects_unknown_skill_area():
    with pytest.raises(ValidationError, match="not in skill_areas"):
        RankingLLM(skill_areas=["A", "B", "C"],
                   rankings=[{"jd_id": "JD-R01", "tier": 1, "reason": "r", "skill_area": "Z"}])


def test_match_status_evidence_rules():
    with pytest.raises(ValidationError):
        MatchLLM(jd_id="JD-R01", status="strong", evidence=[], rationale="r", confidence=1)
    with pytest.raises(ValidationError):
        MatchLLM(jd_id="JD-R01", status="gap", rationale="r", confidence=1,
                 evidence=[{"cv_id": "CV-01", "quote": "abc"}])
    with pytest.raises(ValidationError):
        MatchLLM(jd_id="JD-R01", status="gap", evidence=[], rationale="r", confidence=1.5)


def test_bad_ids_and_extra_fields_rejected():
    with pytest.raises(ValidationError):
        MatchLLM(jd_id="R01", status="gap", evidence=[], rationale="r", confidence=1)
    with pytest.raises(ValidationError):
        MatchLLM(jd_id="JD-R01", status="gap", evidence=[], rationale="r", confidence=1, extra="x")


def test_topic_question_count_and_label():
    q = {"question": "q", "model_answer": "a", "difficulty": "core", "label": "prediction", "jd_ids": ["JD-R01"]}
    base = {"jd_id": "JD-R01", "title": "t", "diagram": None, "code_examples": [],
            "explanation": [{"level": lvl, "heading": "h", "body_md": "b"}
                            for lvl in ("fundamentals", "intermediate", "interview")],
            "common_mistakes": [{"text": "m", "label": "fact", "jd_ids": ["JD-R01"]}],
            "real_world_use": [{"text": "u", "label": "fact", "jd_ids": ["JD-R01"]}]}
    TopicContentLLM.model_validate({**base, "likely_questions": [q] * 3})
    with pytest.raises(ValidationError):
        TopicContentLLM.model_validate({**base, "likely_questions": [q] * 2})
    with pytest.raises(ValidationError):
        TopicContentLLM.model_validate({**base, "likely_questions": [{**q, "label": "fact"}] * 3})
