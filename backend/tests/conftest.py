import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import db
from app.config import get_settings
from app.llm import client as llm_client

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    # Tests never touch a real model: ignore LLM_BACKEND from .env and use the mockable API path.
    monkeypatch.setattr(settings, "llm_backend", "api")
    monkeypatch.setattr(settings, "claude_cli", "/nonexistent/claude")
    db.connect(tmp_path / "test.db")
    yield
    llm_client.set_client(None)


@pytest.fixture
def mbition_html() -> str:
    return (FIXTURES / "mbition_jd.html").read_text()


@pytest.fixture
def resume_pdf() -> bytes:
    return (FIXTURES / "synthetic_resume.pdf").read_bytes()


def load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


class _Block(SimpleNamespace):
    def to_dict(self) -> dict:
        return dict(self.__dict__)


def tool_message(name: str, payload: dict | None, stop_reason: str = "tool_use") -> SimpleNamespace:
    content = [_Block(type="thinking", thinking="", signature="sig")]
    if payload is not None:
        content.append(_Block(type="tool_use", id=f"toolu_{name}", name=name, input=payload))
    else:
        content.append(_Block(type="text", text="Here is my answer in prose."))
    usage = SimpleNamespace(input_tokens=1000, output_tokens=500,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


class FakeStream:
    def __init__(self, message):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.message


class FakeClient:
    """Answers each tool call from a queue of responses keyed by tool name."""

    def __init__(self, responses: dict[str, list]):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["tools"][0]["name"]
        queue = self.responses.get(name)
        if not queue:
            raise AssertionError(f"Unexpected call to {name}")
        resp = queue.pop(0)
        msg = resp if isinstance(resp, SimpleNamespace) else tool_message(name, resp)
        return FakeStream(msg)


@pytest.fixture
def fake_llm():
    def install(responses: dict[str, list]) -> FakeClient:
        c = FakeClient(responses)
        llm_client.set_client(c)
        return c

    return install
