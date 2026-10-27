from typing import Literal

from pydantic import Field

from .common import JdId, Label, Strict


class ExplanationSection(Strict):
    level: Literal["fundamentals", "intermediate", "interview"]
    heading: str
    body_md: str = Field(description="Markdown prose. No code fences; code goes in code_examples.")


class Diagram(Strict):
    kind: Literal["flowchart", "stateDiagram", "sequenceDiagram", "classDiagram"]
    mermaid: str
    description: str = Field(description="Prose description conveying the same information.")


class CodeExample(Strict):
    language: Literal["cpp", "python"]
    title: str
    code: str
    runnable: bool = Field(description="True only for complete programs with main / __main__.")
    explanation: str
    jd_ids: list[JdId] = Field(min_length=1)


class LikelyQuestion(Strict):
    question: str
    model_answer: str
    difficulty: Literal["warm-up", "core", "deep"]
    label: Literal["prediction"]
    jd_ids: list[JdId] = Field(min_length=1)


class Bullet(Strict):
    text: str
    label: Label
    jd_ids: list[JdId] = Field(min_length=1)


class TopicContentLLM(Strict):
    jd_id: JdId
    title: str
    explanation: list[ExplanationSection] = Field(min_length=3)
    diagram: Diagram | None
    code_examples: list[CodeExample] = Field(max_length=3)
    common_mistakes: list[Bullet] = Field(min_length=1)
    real_world_use: list[Bullet] = Field(min_length=1)
    likely_questions: list[LikelyQuestion] = Field(min_length=3, max_length=5)


class CodeCheck(Strict):
    status: Literal["verified", "not_verified"]
    tool: str
    detail: str | None = None


class SnippetFixLLM(Strict):
    code: str


class GapStep(Strict):
    order: int
    what: str
    why: str
    est_hours: float = Field(gt=0, le=200)
    jd_ids: list[JdId] = Field(min_length=1)


class GapPlan(Strict):
    jd_id: JdId
    steps: list[GapStep] = Field(min_length=1)


class GapsLLM(Strict):
    plans: list[GapPlan]
