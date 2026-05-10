"""
Audit B1 + B3 — API-key authentication and per-IP rate limiting.

DEBUG=True mode is the local-dev / test posture: require_api_key is a no-op,
so the FastAPI route layer + slowapi behaviour can be exercised with a
TestClient without juggling secrets. We separately exercise the auth contract
(any/missing key is OK in DEBUG, exact match required when DEBUG=False) by
calling the dependency directly.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Force DEBUG=True before importing the app so the lifespan startup check
# doesn't refuse to boot a test client without a CHATBOT_API_KEY set.
os.environ["DEBUG"] = "true"

from main import app  # noqa: E402  (ordering deliberate)
from services.auth import require_api_key  # noqa: E402
from config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ─── Introspection routes are unauthenticated ─────────────────────────────────
def test_intents_endpoint_open(client):
    response = client.get("/api/v1/chat/intents")
    assert response.status_code == 200
    assert "intents" in response.json()


def test_disasters_endpoint_open(client):
    response = client.get("/api/v1/chat/disasters")
    assert response.status_code == 200
    assert "disasters" in response.json()


def test_root_health_open(client):
    assert client.get("/health").status_code == 200


def test_api_v1_health_open(client):
    assert client.get("/api/v1/health").status_code == 200


# ─── Auth dependency contract (locked Phase 1 decision) ───────────────────────
@pytest.mark.asyncio
async def test_debug_mode_accepts_missing_key():
    """DEBUG=True bypass — missing X-API-Key is accepted."""
    settings = get_settings()
    # Confirm fixture environment puts us in DEBUG mode
    assert settings.DEBUG is True
    await require_api_key(x_api_key=None)  # must NOT raise


@pytest.mark.asyncio
async def test_debug_mode_accepts_any_key():
    settings = get_settings()
    assert settings.DEBUG is True
    await require_api_key(x_api_key="anything-goes")  # must NOT raise


@pytest.mark.asyncio
async def test_non_debug_mode_rejects_missing_key(monkeypatch):
    """DEBUG=False without header → 401."""
    monkeypatch.setattr(get_settings(), "DEBUG", False, raising=False)
    monkeypatch.setattr(get_settings(), "CHATBOT_API_KEY", "secret123", raising=False)
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_non_debug_mode_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "DEBUG", False, raising=False)
    monkeypatch.setattr(get_settings(), "CHATBOT_API_KEY", "secret123", raising=False)
    with pytest.raises(HTTPException) as exc:
        await require_api_key(x_api_key="wrong")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_non_debug_mode_accepts_exact_match(monkeypatch):
    monkeypatch.setattr(get_settings(), "DEBUG", False, raising=False)
    monkeypatch.setattr(get_settings(), "CHATBOT_API_KEY", "secret123", raising=False)
    await require_api_key(x_api_key="secret123")  # must NOT raise


# ─── Rate limiting (slowapi, per-IP) ──────────────────────────────────────────
def test_chat_message_rate_limit_returns_429(client):
    """
    The 31st /chat/message in a minute from one IP returns 429. We use a
    single dummy payload; the chatbot will respond differently each call
    but only the status codes matter.
    """
    settings = get_settings()
    cap = settings.RATE_LIMIT_CHAT_PER_MIN
    payload = {"message": "hello", "region": "pakistan"}

    statuses = []
    for _ in range(cap + 1):
        statuses.append(
            client.post("/api/v1/chat/message", json=payload).status_code
        )

    assert statuses[-1] == 429, (
        f"expected 429 on request #{cap + 1}, got {statuses[-1]} "
        f"(history: {statuses})"
    )
    # Earlier successes should be 200 or 500 (chatbot may not be fully wired
    # in test client) — but never 429 before the cap.
    assert all(s != 429 for s in statuses[:cap])
