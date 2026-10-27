from typing import Literal

from pydantic import Field

from .common import JdId, Quote, Strict


class JDItemLLM(Strict):
    category: Literal["task", "requirement", "nice_to_have"]
    kind: Literal[
        "responsibility", "skill", "language", "tool", "technology",
        "domain", "qualification", "soft_skill", "formal",
    ]
    name: str = Field(description='Short canonical label, e.g. "C++17", "Unit testing".')
    quote: Quote = Field(description="Exact line from the job posting, copied verbatim.")
    section: str = Field(description="Heading of the section, exactly as written.")


class JDExtractionLLM(Strict):
    role_title: str
    company_name: str | None
    location: str | None
    employment_type: str | None
    about_company: list[Quote] = Field(
        max_length=6, description="Verbatim quotes describing the company, team or product."
    )
    items: list[JDItemLLM] = Field(min_length=1, description="All items, in order of appearance.")


class JDItem(JDItemLLM):
    id: JdId
