from typing import Literal

from pydantic import Field, StringConstraints, model_validator
from typing_extensions import Annotated

from .common import JdId, Strict


class RankedRequirement(Strict):
    jd_id: JdId
    tier: Literal[1, 2, 3, 4]
    reason: Annotated[str, StringConstraints(max_length=200)]
    skill_area: str


class RankingLLM(Strict):
    skill_areas: list[str] = Field(min_length=3, max_length=8)
    rankings: list[RankedRequirement] = Field(min_length=1)

    @model_validator(mode="after")
    def areas_are_known(self) -> "RankingLLM":
        allowed = set(self.skill_areas)
        bad = sorted({r.skill_area for r in self.rankings if r.skill_area not in allowed})
        if bad:
            raise ValueError(f"skill_area values not in skill_areas: {bad}")
        return self
