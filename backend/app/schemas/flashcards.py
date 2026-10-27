from typing import Literal

from pydantic import Field

from .common import JdId, Label, Strict


class FlashcardLLM(Strict):
    kind: Literal["concept", "question", "mistake", "code"]
    front: str = Field(description="A question or prompt, answerable from memory in under a minute.")
    back: str = Field(description="The answer: short, specific, at most about 80 words.")
    label: Label
    jd_ids: list[JdId] = Field(min_length=1)


class FlashcardsLLM(Strict):
    cards: list[FlashcardLLM] = Field(min_length=4, max_length=10)
