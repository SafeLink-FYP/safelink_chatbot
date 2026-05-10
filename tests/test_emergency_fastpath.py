"""
Audit B4 — coordinated emergency over-fire fix across all four trigger paths:
1. EMERGENCY_KEYWORDS default no longer contains bare `help` / `emergency`.
2. Keyword-set trigger requires urgency_score >= 0.6 AND >= 1 keyword.
3. The `\\bhelp\\s*me\\b` rule pattern requires a co-occurring anchor word.
4. The hardcoded phrases list in _check_emergency only includes anchored entries.

Real distress phrasings (e.g., "im scared please") still fire via the pure
urgency_score path so we don't deny help to a panicked user.
"""
import pytest

from services import get_chatbot_service
from config import IntentTypes


@pytest.fixture(scope="module")
def chatbot():
    return get_chatbot_service()


# ─── Keyword-set + urgency_score path ─────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "help me with first aid",            # was: hit by bare `help`
        "what is the emergency number",      # was: hit by bare `emergency`
        "sos band ka kaam karta hai",        # was: hit by bare `sos`
        "what to do during heatwave",
        "earthquake safety tips",
        "give me flood preparedness advice",
    ],
)
def test_benign_queries_no_longer_emergency(chatbot, text):
    is_emergency, _ = chatbot._check_emergency(text)
    assert not is_emergency, f"benign text wrongly flagged: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "help me i'm trapped under a wall",
        "fire now help",
        "earthquake happening please send help now",
        "i'm bleeding badly please help immediately",
        "someone is dying right now",
        "gas leak now",
        "i want to kill myself",
    ],
)
def test_real_emergencies_still_fire(chatbot, text):
    is_emergency, score = chatbot._check_emergency(text)
    assert is_emergency, f"real emergency missed: {text!r}"
    assert score >= 0.6


def test_pure_urgency_safety_net(chatbot):
    """
    A distress phrase with no disaster/injury keyword should still fire
    via the urgency_score >= 0.6 safety net so we don't deny help to a
    panicked user typing short bursts.
    """
    is_emergency, _ = chatbot._check_emergency(
        "please help i am scared right now i need help immediately"
    )
    assert is_emergency


def test_help_me_with_first_aid_routes_to_first_aid_or_safety(chatbot):
    """End-to-end: the canonical regression case."""
    intent_result = chatbot.intent_classifier.classify("help me with first aid")
    assert intent_result.intent != IntentTypes.EMERGENCY
    assert intent_result.intent in {
        IntentTypes.FIRST_AID,
        IntentTypes.SAFETY_ADVICE,
        IntentTypes.FALLBACK,  # acceptable if classifier confidence is low
    }
