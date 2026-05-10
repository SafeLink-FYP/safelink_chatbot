"""
Phase 3 — /chat/stream SSE smoke test.

Verifies that the endpoint produces a stream of `delta` events ending with
a `done` event. Body shape mirrors ChatStreamChunk.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["DEBUG"] = "true"
os.environ["USE_LLM"] = "false"  # legacy path is enough for the smoke test

from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _parse_sse_events(text: str) -> list[dict]:
    """
    Minimal SSE parser. Each event is separated by a blank line. The
    `event:` and `data:` lines are mapped into one dict per event.
    """
    events: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        line = line.rstrip("\r")
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current.setdefault("data", "")
            current["data"] += line[len("data:") :].strip()
    if current:
        events.append(current)
    return events


def test_stream_endpoint_yields_delta_then_done(client):
    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "earthquake safety tips", "region": "pakistan"},
    )
    assert response.status_code == 200
    text = response.text
    events = _parse_sse_events(text)
    assert events, f"no SSE events parsed; raw: {text[:200]!r}"

    event_names = [e.get("event") for e in events]
    assert "delta" in event_names, f"no delta events: {event_names}"
    assert event_names[-1] == "done", f"last event isn't 'done': {event_names[-1]}"

    # Final done event must be parseable JSON with done=true.
    final_payload = json.loads(events[-1]["data"])
    assert final_payload["done"] is True
    assert final_payload["message_id"]
    # used_llm is False because we set USE_LLM=false in the env.
    assert final_payload["used_llm"] is False


def test_stream_endpoint_requires_api_key_when_not_debug(monkeypatch, client):
    """Quick contract check: the dependency wired identically to /message."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "DEBUG", False, raising=False)
    monkeypatch.setattr(get_settings(), "CHATBOT_API_KEY", "secret", raising=False)
    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "hi"},
        headers={},
    )
    assert response.status_code == 401
