"""
Phase 5a.1 — Issue 1 regression suite.

Locks the contract that, when `USE_LLM=true` and the intent is SAFETY_ADVICE
or FIRST_AID, the LLM path is the PRIMARY response path even for very short
queries ("flood", "earthquake", "first aid for burns"). Legacy
`_route_intent` is only the safety net when:

  * USE_LLM=false (kill switch)
  * Both LLM providers raise LLMUnavailable

Real LLM calls are NOT made — `LLMService.generate` is monkeypatched to
return a deterministic stub. This keeps the suite fast, free, and
quota-independent.
"""
from __future__ import annotations

import pytest

from config import IntentTypes, get_settings
from models import ChatRequest
from services import get_chatbot_service
from services.llm_service import (
    LLMResponse,
    LLMUnavailable,
    get_llm_service,
    reset_llm_service_for_tests,
)


@pytest.fixture
def chatbot():
    # `get_settings` is lru_cached; tests reach for the live instance and
    # mutate via monkeypatch. Phase 1's auth tests use the same pattern.
    return get_chatbot_service()


# ─── Helpers ────────────────────────────────────────────────────────────────
def _stub_llm_text(text: str):
    """Return a Gemini-style LLMResponse with the given text."""
    return LLMResponse(
        text=text,
        tool_calls=[],
        provider_used="gemini",
        latency_ms=42,
        finish_reason="stop",
    )


def _patch_llm_generate(monkeypatch, stub_response: LLMResponse) -> None:
    """Install a deterministic LLM stub that returns the same response
    regardless of the user message. Keeps the test independent of Gemini
    quota / Groq token budgets."""
    reset_llm_service_for_tests()
    svc = get_llm_service()

    async def _generate(**kwargs):
        return stub_response

    monkeypatch.setattr(svc, "generate", _generate)


def _patch_llm_unavailable(monkeypatch) -> None:
    """Install a stub that raises LLMUnavailable on every call. Used to
    test the safety-net fallback path."""
    reset_llm_service_for_tests()
    svc = get_llm_service()

    async def _generate(**kwargs):
        raise LLMUnavailable("simulated: both providers unavailable")

    monkeypatch.setattr(svc, "generate", _generate)


# ─── Test 1: "flood" → used_llm=True ────────────────────────────────────────
@pytest.mark.asyncio
async def test_short_safety_query_flood_uses_llm(chatbot, monkeypatch):
    """Locks Issue 1: bare 'flood' must hit the LLM path, not the legacy
    KB-chunk template. Pre-Phase-5a.1 the legacy handler returned a
    verbose template with used_llm=False, masking LLM availability."""
    monkeypatch.setattr(get_settings(), "USE_LLM", True, raising=False)
    _patch_llm_generate(
        monkeypatch,
        _stub_llm_text(
            "Move to higher ground immediately. Avoid flood water. "
            "Pakistan emergency: 1122."
        ),
    )

    response = await chatbot.process_message(
        ChatRequest(message="flood", region="pakistan")
    )
    assert response.used_llm is True, (
        f"expected used_llm=True for 'flood'; got {response.used_llm}. "
        f"response_type={response.response_type}"
    )
    assert response.response_type == "safety_advice_llm"
    assert response.intent.intent == IntentTypes.SAFETY_ADVICE
    assert response.intent.sub_intent == "flood"


# ─── Test 2: "earthquake" → used_llm=True ───────────────────────────────────
@pytest.mark.asyncio
async def test_short_safety_query_earthquake_uses_llm(chatbot, monkeypatch):
    monkeypatch.setattr(get_settings(), "USE_LLM", True, raising=False)
    _patch_llm_generate(
        monkeypatch,
        _stub_llm_text("Drop, Cover, Hold On. Stay away from windows."),
    )

    response = await chatbot.process_message(
        ChatRequest(message="earthquake", region="pakistan")
    )
    assert response.used_llm is True
    assert response.intent.intent == IntentTypes.SAFETY_ADVICE
    assert response.intent.sub_intent == "earthquake"


# ─── Test 3: "first aid for burns" → used_llm=True ──────────────────────────
@pytest.mark.asyncio
async def test_first_aid_query_uses_llm(chatbot, monkeypatch):
    monkeypatch.setattr(get_settings(), "USE_LLM", True, raising=False)
    _patch_llm_generate(
        monkeypatch,
        _stub_llm_text(
            "Run cool water over the burn for 15 minutes. Cover loosely."
        ),
    )

    response = await chatbot.process_message(
        ChatRequest(message="first aid for burns", region="pakistan")
    )
    assert response.used_llm is True
    assert response.intent.intent == IntentTypes.FIRST_AID


# ─── Test 4: USE_LLM=false → legacy template, used_llm=False ───────────────
@pytest.mark.asyncio
async def test_use_llm_false_runs_legacy_pipeline(chatbot, monkeypatch):
    """Kill switch regression: with USE_LLM=false, the LLM path must
    not run (even though providers may be reachable). Legacy returns,
    used_llm=False."""
    monkeypatch.setattr(get_settings(), "USE_LLM", False, raising=False)
    # Install an LLM stub that would return text if called — its presence
    # in the response is the failure mode we want to detect.
    _patch_llm_generate(
        monkeypatch,
        _stub_llm_text("THIS_TEXT_MEANS_LLM_WAS_CALLED_INCORRECTLY"),
    )

    response = await chatbot.process_message(
        ChatRequest(message="flood", region="pakistan")
    )
    assert response.used_llm is False
    assert "THIS_TEXT_MEANS_LLM_WAS_CALLED_INCORRECTLY" not in response.response
    # Legacy safety_advice template surfaces the KB chunk title or content.
    assert response.intent.intent == IntentTypes.SAFETY_ADVICE
    assert response.intent.sub_intent == "flood"


# ─── Test 5: LLMUnavailable → legacy fallback safety net works ─────────────
@pytest.mark.asyncio
async def test_llm_unavailable_falls_back_to_legacy(chatbot, monkeypatch):
    """When both LLM providers fail (LLMUnavailable), legacy is the
    documented safety net. used_llm=False; the response comes from the
    legacy KB-chunk template."""
    monkeypatch.setattr(get_settings(), "USE_LLM", True, raising=False)
    _patch_llm_unavailable(monkeypatch)

    response = await chatbot.process_message(
        ChatRequest(message="flood", region="pakistan")
    )
    assert response.used_llm is False, (
        "Legacy fallback should set used_llm=False so observability can "
        "distinguish the two response paths."
    )
    assert response.intent.intent == IntentTypes.SAFETY_ADVICE
    assert response.intent.sub_intent == "flood"
    # The legacy `_handle_safety_advice` surfaces the KB title; confirm
    # we're on that path and not in fallback / weather / something else.
    assert response.response_type == "safety_advice"
