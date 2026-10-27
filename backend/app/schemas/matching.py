from typing import Literal

from pydantic import Field, StringConstraints, model_validator
from typing_extensions import Annotated

from .common import CvId, JdId, Quote, Strict


class Evidence(Strict):
    cv_id: CvId
    quote: Quote


class MatchLLM(Strict):
    jd_id: JdId
    status: Literal["strong", "partial", "gap"]
    evidence: list[Evidence]
    rationale: Annotated[str, StringConstraints(max_length=400)]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def evidence_matches_status(self) -> "MatchLLM":
        if self.status == "gap" and self.evidence:
            raise ValueError(f"{self.jd_id}: status 'gap' must have an empty evidence list")
        if self.status != "gap" and not self.evidence:
            raise ValueError(f"{self.jd_id}: status '{self.status}' needs at least one evidence quote")
        return self


class MatchingLLM(Strict):
    matches: list[MatchLLM] = Field(min_length=1)


class Match(Strict):
    """A match after the deterministic checks. `downgraded` marks a match whose
    evidence quotes all failed verification and whose status was set to gap."""

    jd_id: JdId
    status: Literal["strong", "partial", "gap"]
    evidence: list[Evidence]
    rationale: str
    confidence: float = Field(ge=0, le=1)
    downgraded: bool = False
