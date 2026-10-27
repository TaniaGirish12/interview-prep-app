"""Cache keys. A step's key covers the model, that step's prompt version and only
the inputs it reads, so bumping one prompt version recomputes that step, and
downstream steps rerun only if their own inputs changed."""

import hashlib
import json
from typing import Any

from ..config import get_settings
from ..llm.prompts.steps import VERSION


def cache_key(step: str, *inputs: Any) -> str:
    h = hashlib.sha256()
    for part in (step, get_settings().anthropic_model, str(VERSION[step])):
        h.update(part.encode())
        h.update(b"\x00")
    for value in inputs:
        h.update(hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).digest())
    return f"{step}:{h.hexdigest()}"
