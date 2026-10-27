from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

JdId = Annotated[str, StringConstraints(pattern=r"^JD-[TRN]\d{2,3}$")]
CvId = Annotated[str, StringConstraints(pattern=r"^CV-\d{2,3}$")]
Label = Literal["fact", "prediction"]
Quote = Annotated[str, StringConstraints(min_length=3, max_length=400)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
