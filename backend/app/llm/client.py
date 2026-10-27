"""One structured LLM call per pipeline step.

The model gets exactly one strict tool and is told to call it (forced tool_choice
returns a 400 on this model, so tool_choice is "auto"). The tool input is validated
with Pydantic. If there is no tool call or validation fails, the error is fed back
once and the model tries again. Network errors, 429 and 5xx are retried with
exponential backoff by the SDK (max_retries).
"""

import logging
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from .. import db
from ..config import get_settings
from .prompts.shared import SHARED_RULES
from .tool_schema import tool_definition

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    pass


@dataclass
class ToolSpec(Generic[M]):
    model: type[M]
    name: str
    description: str


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def add(self, u: Any) -> None:
        self.input += u.input_tokens or 0
        self.output += u.output_tokens or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0

    def cost(self) -> float:
        s = get_settings()
        return (self.input * s.price_input + self.output * s.price_output
                + self.cache_read * s.price_cache_read + self.cache_write * s.price_cache_write) / 1e6

    def as_dict(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output,
                "cache_read": self.cache_read, "cache_write": self.cache_write}


_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set. Add it to the .env file and restart the backend.")
        _client = anthropic.AsyncAnthropic(api_key=key, max_retries=4, timeout=600)
    return _client


def set_client(client: Any) -> None:
    """Tests inject a fake client here."""
    global _client
    _client = client


def escape_data(text: str) -> str:
    """Stop data from closing its own wrapper tag and posing as instructions."""
    for tag in ("job_posting_data", "resume_data"):
        text = text.replace(f"</{tag}", f"&lt;/{tag}").replace(f"<{tag}", f"&lt;{tag}")
    return text


def data_block(jd_text: str | None, resume_text: str | None, jd_url: str | None = None) -> str:
    parts = []
    if jd_text is not None:
        src = f' source_url="{jd_url}"' if jd_url else ""
        parts.append(f"<job_posting_data{src}>\n{escape_data(jd_text)}\n</job_posting_data>")
    if resume_text is not None:
        parts.append(f"<resume_data>\n{escape_data(resume_text)}\n</resume_data>")
    return "\n\n".join(parts)


async def call_tool(
    spec: ToolSpec[M],
    user_content: str,
    *,
    data: str,
    step: str,
    effort: str,
    cache: bool = False,
    analysis_id: int | None = None,
    ref: str | None = None,
    max_tokens: int = 32000,
) -> M:
    settings = get_settings()
    if settings.llm_backend == "claude-code":
        from .cli_backend import call_cli  # local import: cli_backend imports this module

        return await call_cli(spec, user_content, data=data, step=step, effort=effort,
                              analysis_id=analysis_id, ref=ref)
    client = get_client()
    system: list[dict[str, Any]] = [
        {"type": "text", "text": SHARED_RULES},
        {"type": "text", "text": data, **({"cache_control": {"type": "ephemeral"}} if cache else {})},
    ]
    extra: dict[str, Any] = {}
    if settings.refusal_fallback:
        extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
    usage = Usage()
    last_error = ""
    succeeded = False
    try:
        for attempt in (1, 2):
            async with client.beta.messages.stream(
                model=settings.anthropic_model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool_definition(spec.model, spec.name, spec.description)],
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                output_config={"effort": effort},
                messages=messages,
                **extra,
            ) as stream:
                msg = await stream.get_final_message()
            usage.add(msg.usage)

            if msg.stop_reason == "refusal":
                raise LLMError(f"The model declined this request ({step}).")
            if msg.stop_reason == "max_tokens":
                raise LLMError(f"The response for {step} hit the output limit before finishing.")

            block = next((b for b in msg.content if b.type == "tool_use" and b.name == spec.name), None)
            if block is None:
                last_error = f"No {spec.name} tool call in the response."
                feedback: list[dict[str, Any]] = [{
                    "type": "text",
                    "text": f"You did not call the {spec.name} tool. Call {spec.name} now with the complete result.",
                }]
            else:
                try:
                    parsed = spec.model.model_validate(block.input)
                    succeeded = True
                    return parsed
                except ValidationError as e:
                    last_error = _format_errors(e)
                    feedback = [{
                        "type": "tool_result", "tool_use_id": block.id, "is_error": True,
                        "content": f"Validation failed:\n{last_error}\n\nCall {spec.name} again with corrected input.",
                    }]
            log.warning("%s attempt %d failed: %s", step, attempt, last_error)
            messages = messages + [
                {"role": "assistant", "content": [b.to_dict() for b in msg.content]},
                {"role": "user", "content": feedback},
            ]
        raise LLMError(f"{step}: output failed validation twice. Last error: {last_error}")
    except anthropic.APIStatusError as e:
        raise LLMError(f"{step}: API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"{step}: could not reach the Anthropic API ({e}).") from e
    finally:
        if usage.input or usage.output:
            db.log_call(analysis_id, step, ref, usage.as_dict(), usage.cost(), ok=succeeded)


def _format_errors(e: ValidationError) -> str:
    lines = []
    for err in e.errors()[:20]:
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']}")
    return "\n".join(lines)
