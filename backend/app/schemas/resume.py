from typing import Literal

from pydantic import Field

from .common import CvId, Quote, Strict


class CVItemLLM(Strict):
    category: Literal["role", "project", "skill", "achievement", "education", "certification"]
    title: str
    context: str | None = Field(description="Employer or project this line belongs to, if clear.")
    quote: Quote = Field(description="Exact line from the resume, copied verbatim.")


class ResumeExtractionLLM(Strict):
    items: list[CVItemLLM] = Field(min_length=1)


class CVItem(CVItemLLM):
    id: CvId
