"""
Phase 3 — Self-harm / crisis fast-path tests.

Locked O10: hand-curated phrase list. False positives route to crisis
resources (low harm); false negatives route to LLM (high harm). The list
is intentionally broad.

These tests exercise the routing — full content review of the template
copy is the human reviewer's job before merge.
"""
import pytest

from services.chatbot_service import (
    CRISIS_PHRASES,
    CRISIS_TEMPLATE,
    _is_crisis,
    get_chatbot_service,
)
from models import ChatRequest


@pytest.fixture
def chatbot():
    return get_chatbot_service()


# ─── Phrase detector ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "I want to kill myself.",
        "i'm going to end my life tonight",
        "i feel suicidal please help",
        "i can't go on like this anymore",
        "There's no reason to live.",
        "i wanna die",
        "tired of being alive",
        "I want to hurt myself",
        "thinking about taking my own life",
        "goodbye world, this is my last message",
    ],
)
def test_crisis_phrases_detected(text):
    assert _is_crisis(text), f"expected crisis route for {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "earthquake safety tips please",
        "what to do during a flood",
        "how is your day",
        "mental health support after disaster",
        "i feel sad about losing my house",       # sad ≠ crisis
        "the building killed itself",              # absurd, no self-harm
        "i would die for cricket",                 # idiomatic
    ],
)
def test_non_crisis_phrases_not_detected(text):
    assert not _is_crisis(text), f"unexpected crisis route for {text!r}"


# ─── Whole-pipeline routing ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_crisis_message_routes_to_crisis_template(chatbot):
    response = await chatbot.process_message(
        ChatRequest(message="I want to kill myself", region="pakistan")
    )
    assert response.response_type == "crisis"
    assert response.used_llm is False
    assert "Umang" in response.response or "0311-7786264" in response.response
    assert "115" in response.response
    # The template MUST surface mental-health helplines.
    helpline_numbers = {h.number for h in response.helplines}
    assert "115" in helpline_numbers


@pytest.mark.asyncio
async def test_crisis_template_carries_critical_urgency(chatbot):
    response = await chatbot.process_message(
        ChatRequest(message="i'm going to end my life", region="pakistan")
    )
    from models import UrgencyLevel

    assert response.urgency_level == UrgencyLevel.CRITICAL
    assert response.is_emergency is True


@pytest.mark.asyncio
async def test_non_crisis_message_does_not_hit_crisis_path(chatbot):
    response = await chatbot.process_message(
        ChatRequest(message="how do I do CPR", region="pakistan")
    )
    assert response.response_type != "crisis"


def test_phrase_list_is_nonempty_and_owner_review_flagged():
    """Locked O10 — the list is curated, broad, and requires owner review."""
    assert len(CRISIS_PHRASES) >= 30
    # Must contain at least one phrase from each broad category.
    cats = (
        "kill myself",
        "no reason to live",
        "harm myself",
    )
    for c in cats:
        assert any(c in p for p in CRISIS_PHRASES), f"missing category like {c!r}"
