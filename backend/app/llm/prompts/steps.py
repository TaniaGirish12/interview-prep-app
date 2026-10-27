"""Per-step instructions (the user message). Bump a step's VERSION when its prompt or
schema changes; that invalidates the cache for that step only."""

import json

from ...schemas import (
    FlashcardsLLM,
    GapsLLM,
    JDExtractionLLM,
    MatchingLLM,
    RankingLLM,
    ResumeExtractionLLM,
    SnippetFixLLM,
    TopicContentLLM,
)
from ..client import ToolSpec

VERSION = {"jd": 1, "rank": 1, "resume": 1, "match": 1, "topic": 1, "fix": 1, "gaps": 1, "cards": 1}

JD_TOOL = ToolSpec(JDExtractionLLM, "extract_job_posting",
                   "Record every item of the job posting, each with its verbatim quote.")
RANK_TOOL = ToolSpec(RankingLLM, "rank_requirements",
                     "Record the interview-importance tier and skill area of every JD item.")
RESUME_TOOL = ToolSpec(ResumeExtractionLLM, "extract_resume",
                       "Record every role, project, skill, achievement and education entry of the resume.")
MATCH_TOOL = ToolSpec(MatchingLLM, "match_requirements",
                      "Record how well the resume covers each JD item, with verbatim evidence.")
TOPIC_TOOL = ToolSpec(TopicContentLLM, "write_topic_notes",
                      "Record interview study notes for one JD requirement.")
FIX_TOOL = ToolSpec(SnippetFixLLM, "fix_snippet", "Record the corrected code snippet.")
CARDS_TOOL = ToolSpec(FlashcardsLLM, "write_flashcards",
                      "Record spaced-repetition flashcards for one JD requirement's topic notes.")
GAPS_TOOL = ToolSpec(GapsLLM, "plan_gap_learning",
                     "Record an ordered learning plan for each listed JD requirement.")


def jd_extraction() -> str:
    return """\
Call extract_job_posting. Read the job posting section by section, in order, and extract every item:
- each responsibility → category "task", kind "responsibility"
- each requirement or qualification → category "requirement"
- each nice-to-have, preferred or "is a plus" item → category "nice_to_have"

Split compound lines: "experience in C++ and Python" gives one item for C++ and one for Python, both quoting the same line. Give every programming language, tool and technology its own item with the right kind. Formal requirements such as enrolment status, working hours, work permit or spoken languages are items with kind "formal". `section` is the heading exactly as written in the posting. Skip benefits, legal text and application instructions unless they state a requirement.

Also fill role_title, company_name, location and employment_type if the posting states them (otherwise null), and up to 6 about_company quotes that describe the company, team or product."""


def _jd_items_json(jd_items: list[dict], extra: dict[str, dict] | None = None) -> str:
    rows = []
    for i in jd_items:
        row = {k: i[k] for k in ("id", "category", "kind", "name", "section", "quote")}
        if extra and i["id"] in extra:
            row.update(extra[i["id"]])
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False, indent=1)


def ranking(jd_items: list[dict]) -> str:
    return f"""\
Call rank_requirements for these JD items:

<jd_items>
{_jd_items_json(jd_items)}
</jd_items>

First choose 4 to 8 short skill-area labels that together cover every item (for example "C++ & concurrency", "Testing & CI"); these become the axes of a radar chart. Then rank every item exactly once:
- Tier 1: central to the role; appears in the title or in both tasks and requirements, or is stated as a must. Very likely to be tested directly.
- Tier 2: an explicit requirement mentioned once, or a responsibility that implies a testable skill.
- Tier 3: a nice-to-have, or a supporting tool.
- Tier 4: peripheral to a technical interview (formal requirements, general soft skills).

`reason` is one line naming the evidence in the posting, for example "appears in both tasks and profile". Every skill_area must be one of your skill_areas labels."""


def resume_extraction() -> str:
    return """\
Call extract_resume. Extract, in order, every role, project, skill, achievement, education entry and certification from <resume_data>. Each item quotes exactly one line or bullet. For skill lists, make one item per skill and quote the list line (or the part of it naming the skill). Keep numbers exactly as written; never round or infer them. `context` names the employer or project the line belongs to, if the resume makes that clear; otherwise null."""


def matching(jd_items: list[dict], rankings: dict[str, dict], cv_items: list[dict]) -> str:
    tiers = {k: {"tier": v["tier"]} for k, v in rankings.items()}
    cv = [{k: c[k] for k in ("id", "category", "title", "context", "quote")} for c in cv_items]
    return f"""\
Call match_requirements with exactly one match per JD id.

<jd_items>
{_jd_items_json(jd_items, tiers)}
</jd_items>

<cv_items>
{json.dumps(cv, ensure_ascii=False, indent=1)}
</cv_items>

- strong: the resume shows the candidate doing this, in a role or project.
- partial: related or adjacent experience, or the skill is only listed without demonstrated use.
- gap: no evidence. Use an empty evidence list.

Each evidence quote must be copied exactly from the quote of the CV item you cite (the whole quote or a contiguous part of it). `confidence` is how sure you are of the status (1.0 = unambiguous); use lower values when the resume wording is vague. `rationale` is one or two sentences."""


def topic(jd_item: dict, ranking_row: dict, match: dict, cv_by_id: dict[str, dict], all_items: list[dict]) -> str:
    evidence = [
        {"cv_id": e["cv_id"], "quote": e["quote"], "title": cv_by_id.get(e["cv_id"], {}).get("title")}
        for e in match["evidence"]
    ]
    others = [{"id": i["id"], "name": i["name"]} for i in all_items]
    return f"""\
Call write_topic_notes for {jd_item['id']}: "{jd_item['name']}".

<requirement>
{json.dumps({**{k: jd_item[k] for k in ('id', 'category', 'kind', 'name', 'section', 'quote')},
             'tier': ranking_row['tier'], 'tier_reason': ranking_row['reason'],
             'status': match['status'], 'match_rationale': match['rationale']}, ensure_ascii=False, indent=1)}
</requirement>

<resume_evidence>
{json.dumps(evidence, ensure_ascii=False, indent=1)}
</resume_evidence>

<all_jd_ids>
{json.dumps(others, ensure_ascii=False)}
</all_jd_ids>

Write study notes for an interview for this role.
- explanation: build up from fundamentals to the depth an interviewer for this role would probe, with at least one section per level (fundamentals, intermediate, interview), in that order. Status is "{match['status']}": for a gap, start from first principles; for a strong match, spend less time on basics and more on interview-level depth and how the candidate's quoted experience connects to it.
- diagram: include a Mermaid diagram only where structure helps (state machines, observer flow, MVC, thread interactions, CI stages, build flow); otherwise null. Use valid Mermaid syntax for the chosen kind (flowchart → "flowchart TD", stateDiagram → "stateDiagram-v2"), quote node labels that contain punctuation, and write a description that conveys the same information in prose.
- code_examples: 0 to 3 examples in the languages the posting uses (C++ or Python). Set runnable only for complete programs with a main function (C++) or an if __name__ == "__main__": block (Python). Runnable programs must finish within a second and need no input. Multithreaded C++ must use proper synchronisation.
- common_mistakes and real_world_use: specific to this requirement and, where possible, to the domain of the posting.
- likely_questions: 3 to 5 questions, labelled "prediction", ordered warm-up → deep, each with a model answer. Where an answer should draw on the candidate's experience, use the quoted resume evidence; otherwise use placeholders.

Cite {jd_item['id']} on every item; also cite other ids from <all_jd_ids> where an item genuinely covers them."""


def fix_snippet(language: str, code: str, tool: str, detail: str) -> str:
    lang = "C++17" if language == "cpp" else "Python 3.10"
    return f"""\
This {lang} snippet failed the check `{tool}`:

<snippet>
{code}
</snippet>

<check_output>
{detail}
</check_output>

Call fix_snippet with the full corrected code. Keep its purpose, keep it minimal, and make sure it passes the check."""


def gaps(rows: list[dict]) -> str:
    return f"""\
Call plan_gap_learning for these JD requirements (partial matches and gaps), listed in priority order:

<requirements>
{json.dumps(rows, ensure_ascii=False, indent=1)}
</requirements>

For each requirement, give the ordered steps to reach interview level, each with a realistic estimate in hours for someone with the candidate's quoted background. Steps are concrete (what to read, build or practise), specific to the posting's domain, and cite the JD ids they serve. Return one plan per listed requirement, in the same order."""


def flashcards(topic: dict, all_items: list[dict]) -> str:
    notes = {
        "jd_id": topic["jd_id"], "title": topic["title"],
        "explanation": [{"level": s["level"], "heading": s["heading"], "body_md": s["body_md"]} for s in topic["explanation"]],
        "code_examples": [{"title": c["title"], "language": c["language"], "explanation": c["explanation"]}
                          for c in topic["code_examples"]],
        "common_mistakes": [b["text"] for b in topic["common_mistakes"]],
        "likely_questions": [{"question": q["question"], "model_answer": q["model_answer"]} for q in topic["likely_questions"]],
    }
    others = [{"id": i["id"], "name": i["name"]} for i in all_items]
    return f"""\
Call write_flashcards for {topic['jd_id']}: "{topic['title']}".

<topic_notes>
{json.dumps(notes, ensure_ascii=False, indent=1)}
</topic_notes>

<all_jd_ids>
{json.dumps(others, ensure_ascii=False)}
</all_jd_ids>

Write 6 to 8 flashcards that help the candidate recall this topic in an interview, built only from <topic_notes>.
- Mix the kinds: "concept" (a definition or why/when), "question" (a likely interview question in short form), "mistake" (a common mistake and the fix), "code" (what a short piece of code does or how to write it, described in words; at most 3 lines of code on a card).
- One idea per card. The front is a direct question; the back is the answer in at most about 80 words, specific and correct.
- Label "fact" only for what the posting or resume states; general technical knowledge and likely questions are "prediction".
- Do not invent the candidate's experience; where a card is about their experience, keep [PLACEHOLDERS] as in the notes.
- Cite {topic['jd_id']} on every card; also cite other ids from <all_jd_ids> where a card genuinely covers them."""
