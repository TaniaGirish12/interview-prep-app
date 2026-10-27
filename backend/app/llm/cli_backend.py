"""LLM backend that runs the Claude Code CLI headless (`claude -p`) on the user's
Claude subscription login instead of an API key.

Same contract as the API backend: one JSON schema per step (passed with
--json-schema), Pydantic validation, and one retry with the errors fed back.
The CLI runs with no tools, no settings, no session persistence and an empty
working directory, so it acts as a plain model call. API keys are removed from
its environment so it can never fall back to per-token API billing.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .. import db
from ..config import get_settings
from .client import LLMError, ToolSpec, Usage, _format_errors
from .prompts.shared import SHARED_RULES
from .tool_schema import input_schema

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)

CLI_OUTPUT_NOTE = """\

## Output in this environment
There are no tools here. When the user message says to call a tool, return the result as your final structured JSON output instead; it must match the JSON schema you were given. Do not wrap it in prose or code fences.
"""

# Never let the CLI pick up API credentials: it must use the subscription login.
_STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK",
              "CLAUDE_CODE_USE_VERTEX")


def cli_path() -> str | None:
    configured = get_settings().claude_cli
    found = shutil.which(configured) or (configured if Path(configured).is_file() else None)
    if found is None and configured == "claude":
        # The native installer puts the CLI here, which is not always on a server's PATH.
        default = Path.home() / ".local" / "bin" / "claude"
        found = str(default) if default.is_file() else None
    return found


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


async def _run_cli(prompt: str, system: str, schema: dict, effort: str) -> dict[str, Any]:
    exe = cli_path()
    if exe is None:
        raise LLMError(
            "The `claude` command was not found. Install Claude Code (see README), run `claude` once to log in, "
            "or set CLAUDE_CLI in .env to its full path."
        )
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="interview-prep-cli-") as tmp:
        sys_file = Path(tmp, "system.txt")
        sys_file.write_text(system)
        args = [
            exe, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt-file", str(sys_file),
            "--tools", "",
            "--model", settings.anthropic_model,
            "--effort", effort,
            "--no-session-persistence",
            "--setting-sources", "",
        ]
        proc = await asyncio.create_subprocess_exec(
            *args, cwd=tmp, env=_env(),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), settings.cli_timeout_s)
        except asyncio.TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise LLMError(f"The claude CLI did not finish within {settings.cli_timeout_s:.0f}s.") from e
    try:
        result = json.loads(out.decode())
    except json.JSONDecodeError as e:
        detail = (err.decode(errors="replace") or out.decode(errors="replace")).strip()[:500]
        raise LLMError(f"The claude CLI failed (exit {proc.returncode}): {detail}") from e
    if result.get("is_error"):
        message = str(result.get("result") or result.get("terminal_reason") or "unknown error")
        if "not logged in" in message.lower() or "/login" in message:
            message = "The claude CLI is not logged in. Run `claude` in a terminal once and log in with your Claude account."
        elif "usage limit" in message.lower() or "rate limit" in message.lower():
            message = f"Your Claude plan's usage limit was reached: {message}"
        raise LLMError(message)
    return result


def _payload(result: dict[str, Any]) -> Any:
    """Structured output if the CLI returns it separately, else the JSON in the result text."""
    if result.get("structured_output") is not None:
        return result["structured_output"]
    text = str(result.get("result") or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _usage(result: dict[str, Any]) -> Usage:
    u = result.get("usage") or {}
    return Usage(input=u.get("input_tokens") or 0, output=u.get("output_tokens") or 0,
                 cache_read=u.get("cache_read_input_tokens") or 0,
                 cache_write=u.get("cache_creation_input_tokens") or 0)


async def call_cli(
    spec: ToolSpec[M], user_content: str, *, data: str, step: str, effort: str,
    analysis_id: int | None = None, ref: str | None = None,
) -> M:
    system = SHARED_RULES + CLI_OUTPUT_NOTE + "\n" + data
    schema = input_schema(spec.model)
    prompt = user_content
    total = Usage()
    last_error = ""
    succeeded = False
    try:
        for attempt in (1, 2):
            result = await _run_cli(prompt, system, schema, effort)
            u = _usage(result)
            for f in ("input", "output", "cache_read", "cache_write"):
                setattr(total, f, getattr(total, f) + getattr(u, f))
            try:
                raw = _payload(result)
            except (json.JSONDecodeError, TypeError) as e:
                last_error = f"The output was not valid JSON: {e}"
                raw = None
            if raw is not None:
                try:
                    parsed = spec.model.model_validate(raw)
                    succeeded = True
                    return parsed
                except ValidationError as e:
                    last_error = _format_errors(e)
            log.warning("%s attempt %d failed (claude-code): %s", step, attempt, last_error)
            previous = json.dumps(raw, ensure_ascii=False) if raw is not None else str(result.get("result", ""))[:20000]
            prompt = (
                f"{user_content}\n\n<previous_attempt>\n{previous}\n</previous_attempt>\n\n"
                f"Your previous output failed validation:\n{last_error}\n\n"
                "Return the complete corrected result as JSON matching the schema."
            )
        raise LLMError(f"{step}: output failed validation twice. Last error: {last_error}")
    finally:
        if total.input or total.output:
            # Subscription usage is not billed per token, so the cost is recorded as 0.
            db.log_call(analysis_id, step, ref, total.as_dict(), 0.0, ok=succeeded)
