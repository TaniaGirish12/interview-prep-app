"""The claude-code backend, driven by a fake `claude` executable."""

import json
import stat
import sys

import pytest

from app import db
from app.config import get_settings
from app.llm.client import LLMError, call_tool
from app.llm.prompts import steps as P

RESUME_OK = {"items": [{"category": "skill", "title": "C++", "context": None,
                        "quote": "Languages: C++, Python, Java, TypeScript"}]}
FAKE = """#!{python}
import json, os, sys
from pathlib import Path
state = Path({state!r})
queue = json.loads((state / "queue.json").read_text())
reply = queue.pop(0)
(state / "queue.json").write_text(json.dumps(queue))
calls = json.loads((state / "calls.json").read_text()) if (state / "calls.json").exists() else []
calls.append({{"argv": sys.argv[1:], "stdin": sys.stdin.read(),
               "api_key": os.environ.get("ANTHROPIC_API_KEY"), "cwd": os.getcwd()}})
(state / "calls.json").write_text(json.dumps(calls))
print(json.dumps(reply))
"""


def _result(payload=None, *, text=None, is_error=False):
    out = {"type": "result", "is_error": is_error, "result": text if text is not None else "",
           "usage": {"input_tokens": 1200, "output_tokens": 300,
                     "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    if payload is not None:
        out["structured_output"] = payload
    return out


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    settings = get_settings()
    exe = tmp_path / "claude"
    exe.write_text(FAKE.format(python=sys.executable, state=str(tmp_path)))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(settings, "llm_backend", "claude-code")
    monkeypatch.setattr(settings, "claude_cli", str(exe))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")

    def install(*replies):
        (tmp_path / "queue.json").write_text(json.dumps(list(replies)))
        return lambda: json.loads((tmp_path / "calls.json").read_text())

    return install


async def test_structured_output_validates(fake_cli):
    calls = fake_cli(_result(RESUME_OK))
    out = await call_tool(P.RESUME_TOOL, "Call extract_resume.", data="<resume_data>x</resume_data>",
                          step="resume", effort="medium", analysis_id=7)
    assert out.items[0].title == "C++"
    (call,) = calls()
    argv = call["argv"]
    assert argv[0] == "-p" and argv[argv.index("--output-format") + 1] == "json"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["additionalProperties"] is False and "items" in schema["properties"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == get_settings().anthropic_model
    assert argv[argv.index("--effort") + 1] == "medium"
    assert "--no-session-persistence" in argv
    assert call["stdin"] == "Call extract_resume."
    assert call["api_key"] is None  # subscription only: the API key is stripped
    assert "interview-prep-cli-" in call["cwd"]
    cost = db.analysis_cost(7)
    assert cost["calls"] == 1 and cost["usd"] == 0 and cost["input"] == 1200


async def test_retry_with_errors_then_success(fake_cli):
    bad = {"items": [{"category": "hobby", "title": "x", "context": None, "quote": "abc"}]}
    calls = fake_cli(_result(bad), _result(text=f"```json\n{json.dumps(RESUME_OK)}\n```"))
    out = await call_tool(P.RESUME_TOOL, "Call extract_resume.", data="d", step="resume", effort="low")
    assert out.items[0].quote.startswith("Languages")
    second = calls()[1]["stdin"]
    assert "<previous_attempt>" in second and "items.0.category" in second


async def test_two_failures_raise(fake_cli):
    fake_cli(_result(text="no json here"), _result(text="still none"))
    with pytest.raises(LLMError, match="failed validation twice"):
        await call_tool(P.RESUME_TOOL, "x", data="d", step="resume", effort="low")


async def test_not_logged_in_message(fake_cli):
    fake_cli(_result(text="Not logged in · Please run /login", is_error=True))
    with pytest.raises(LLMError, match="not logged in"):
        await call_tool(P.RESUME_TOOL, "x", data="d", step="resume", effort="low")


async def test_missing_cli(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_backend", "claude-code")
    monkeypatch.setattr(settings, "claude_cli", "/nonexistent/claude")
    with pytest.raises(LLMError, match="was not found"):
        await call_tool(P.RESUME_TOOL, "x", data="d", step="resume", effort="low")
