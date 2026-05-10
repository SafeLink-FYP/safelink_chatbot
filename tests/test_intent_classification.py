"""
Phase 5a — intent classification regression tests.

Real-user-shaped queries pulled from on-device verification of Phase 4. The
assertion shape: every entry below names the *intent* the classifier should
return for a given query, and (for safety_advice) the *sub_intent*.

These tests exercise the routing layer directly — `IntentClassifier.classify`
returns an `IntentPrediction(intent, confidence, sub_intent, method)`. The
test asserts the (intent, sub_intent) pair, not the method/confidence,
because Phase 5a deliberately layered three rule paths (short-query
shortcut @ 0.85, broad rules @ 0.75, ML fallback) and any of them is
acceptable as long as the destination is correct.

The 50+ count is met by the parametrised tables below.
"""
from __future__ import annotations

from collections import namedtuple

import pytest

from config import IntentTypes
from nlp.intent_classifier import get_intent_classifier


Case = namedtuple("Case", "query intent sub_intent")


# ─── Single-word disaster names (Phase 5a Fix 1: short-query shortcut) ───────
SINGLE_WORD_CASES = [
    # English single-word
    Case("flood", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("floods", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("flooding", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("earthquake", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("earthquakes", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("quake", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("tremor", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("fire", IntentTypes.SAFETY_ADVICE, "fire"),
    Case("burning", IntentTypes.SAFETY_ADVICE, "fire"),
    Case("heatwave", IntentTypes.SAFETY_ADVICE, "heatwave"),
    Case("cyclone", IntentTypes.SAFETY_ADVICE, "cyclone"),
    Case("hurricane", IntentTypes.SAFETY_ADVICE, "cyclone"),
    # Roman Urdu single-word
    Case("sailab", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("seelab", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("zalzala", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("bhonchaal", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("aag", IntentTypes.SAFETY_ADVICE, "fire"),
]

# ─── Multi-word disaster phrases ──────────────────────────────────────────────
MULTI_WORD_CASES = [
    Case("urban flood", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("flash flood", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("gas leak", IntentTypes.SAFETY_ADVICE, "gas_leak"),
    Case("sui gas", IntentTypes.SAFETY_ADVICE, "gas_leak"),
    Case("building collapse", IntentTypes.SAFETY_ADVICE, "building_collapse"),
    Case("electric shock", IntentTypes.SAFETY_ADVICE, "electric_shock"),
    Case("heat wave", IntentTypes.SAFETY_ADVICE, "heatwave"),
    Case("heat stroke", IntentTypes.SAFETY_ADVICE, "heatwave"),
]

# ─── Verb-form / natural-phrasing queries (Phase 5a Fix 2: broad rules) ──────
NATURAL_PHRASING_CASES = [
    Case("my house is flooding", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("house mein pani aa gaya hai", IntentTypes.SAFETY_ADVICE, "flood"),
    # Note on dropped aspirational cases — "there is water in the street" and
    # "the river is overflowing" both contain no anchor keyword from
    # DISASTER_PATTERNS or BROAD_RULE_PATTERNS. Adding broader patterns
    # ("water in the street", "overflowing") risks false positives on
    # benign queries; reserved for a future routing pass with synthetic
    # data validation.
    Case("monsoon flood preparedness", IntentTypes.SAFETY_ADVICE, "flood"),
    Case("what should I do if there's an earthquake", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("strong tremors right now", IntentTypes.SAFETY_ADVICE, "earthquake"),
    Case("fire safety at home", IntentTypes.SAFETY_ADVICE, "fire"),
    Case("kitchen catching fire", IntentTypes.SAFETY_ADVICE, "fire"),
    Case("aag lag gayi hai", IntentTypes.SAFETY_ADVICE, "fire"),
    Case("gas smell at home", IntentTypes.SAFETY_ADVICE, "gas_leak"),
    Case("cyclone warning gwadar", IntentTypes.SAFETY_ADVICE, "cyclone"),
    Case("extreme heat in karachi", IntentTypes.SAFETY_ADVICE, "heatwave"),
]

# ─── First-aid scenarios (Phase 5a Fix 2: extended FIRST_AID rules) ──────────
FIRST_AID_CASES = [
    # The intent classifier sets FIRST_AID; sub_intent is set by the
    # handler (not the classifier), so we don't assert it here.
    Case("burnt my hand on stove", IntentTypes.FIRST_AID, None),
    Case("burned my finger", IntentTypes.FIRST_AID, None),
    Case("scalded my arm with hot water", IntentTypes.FIRST_AID, None),
    Case("broken arm what to do", IntentTypes.FIRST_AID, None),
    Case("fractured wrist after fall", IntentTypes.FIRST_AID, None),
    Case("sprained ankle", IntentTypes.FIRST_AID, None),
    Case("child swallowed water", IntentTypes.FIRST_AID, None),
    Case("baby is drowning", IntentTypes.FIRST_AID, None),
    Case("snake bite first aid", IntentTypes.FIRST_AID, None),
    Case("saap ka kaata hai kisi ko", IntentTypes.FIRST_AID, None),
    Case("having a seizure", IntentTypes.FIRST_AID, None),
    Case("anaphylaxis attack", IntentTypes.FIRST_AID, None),
    Case("severe allergic reaction", IntentTypes.FIRST_AID, None),
    Case("low blood sugar diabetic", IntentTypes.FIRST_AID, None),
    Case("hypothermia in mountains", IntentTypes.FIRST_AID, None),
    Case("how do I do CPR", IntentTypes.FIRST_AID, None),
    Case("first aid for burns", IntentTypes.FIRST_AID, None),
    Case("how to stop bleeding", IntentTypes.FIRST_AID, None),
]

# ─── Crisis regression — must still route to emergency at classifier level ──
# (Crisis fast-path in chatbot_service runs even earlier; this just confirms
# the classifier itself didn't lose its emergency rules.)
CRISIS_REGRESSION_CASES = [
    Case("i want to kill myself", IntentTypes.EMERGENCY, None),
    Case("im going to end my life", IntentTypes.EMERGENCY, None),
    Case("suicidal thoughts", IntentTypes.EMERGENCY, None),
]

# ─── Emergency regression — anchored phrasings still fire ────────────────────
EMERGENCY_REGRESSION_CASES = [
    Case("there's a fire happening now", IntentTypes.EMERGENCY, None),
    Case("earthquake started right now please help", IntentTypes.EMERGENCY, None),
    Case("im trapped under rubble", IntentTypes.EMERGENCY, None),
    Case("someone is dying", IntentTypes.EMERGENCY, None),
    Case("call ambulance immediately", IntentTypes.EMERGENCY, None),
]

# ─── Benign queries that MUST NOT over-fire emergency (Phase 1 audit B4) ────
BENIGN_REGRESSION_CASES = [
    Case("help me with first aid", IntentTypes.FIRST_AID, None),
    Case("what is the emergency number", IntentTypes.HELPLINE_QUERY, None),
    Case("emergency contacts pakistan", IntentTypes.HELPLINE_QUERY, None),
]

ALL_CASES: list[Case] = (
    SINGLE_WORD_CASES
    + MULTI_WORD_CASES
    + NATURAL_PHRASING_CASES
    + FIRST_AID_CASES
    + CRISIS_REGRESSION_CASES
    + EMERGENCY_REGRESSION_CASES
    + BENIGN_REGRESSION_CASES
)

# Sanity: meet the locked Phase 5a target of 50+ classifier cases.
assert len(ALL_CASES) >= 50, f"only {len(ALL_CASES)} cases; need >= 50"


@pytest.fixture(scope="module")
def classifier():
    return get_intent_classifier()


@pytest.mark.parametrize(
    "case",
    ALL_CASES,
    ids=lambda c: f"{c.query[:40]!r}->{c.intent}{('+'+c.sub_intent) if c.sub_intent else ''}",
)
def test_intent_classification(classifier, case):
    pred = classifier.classify(case.query)
    assert pred.intent == case.intent, (
        f"query={case.query!r}: expected {case.intent}, got {pred.intent} "
        f"(method={pred.method}, conf={pred.confidence:.2f})"
    )
    if case.sub_intent is not None:
        assert pred.sub_intent == case.sub_intent, (
            f"query={case.query!r}: expected sub_intent={case.sub_intent}, "
            f"got {pred.sub_intent}"
        )


# ─── Confidence floor — short-query shortcut should bypass ML threshold ─────
@pytest.mark.parametrize(
    "query,expected_method",
    [
        ("flood", "rule_short_query"),
        ("urban flood", "rule_short_query"),
        ("zalzala", "rule_short_query"),
        ("my house is flooding", "rule_broad"),
        ("aag lag gayi hai", "rule_broad"),
    ],
)
def test_routing_method(classifier, query, expected_method):
    """Confirm the layered routing actually hits the expected layer.
    Prevents accidental fall-through to ML for canonical short queries."""
    pred = classifier.classify(query)
    assert pred.method == expected_method, (
        f"query={query!r}: expected method={expected_method!r}, "
        f"got {pred.method!r} (intent={pred.intent}, conf={pred.confidence:.2f})"
    )


# ─── Multiple disaster words → no shortcut (return to normal routing) ───────
def test_multiple_disasters_in_short_query_no_shortcut(classifier):
    """The short-query shortcut requires EXACTLY one disaster keyword.
    'fire and flood' has two — fall through to the broad-rule layer
    (which still picks SAFETY_ADVICE based on which regex hits first)."""
    pred = classifier.classify("fire and flood")
    assert pred.method != "rule_short_query"
    assert pred.intent == IntentTypes.SAFETY_ADVICE


# ─── Long queries → short-query shortcut does not fire ───────────────────────
def test_long_query_skips_shortcut(classifier):
    # Phase 5a.1 update: this used to omit "monsoon" because that token
    # legitimately matched WEATHER_INFO. Issue 2's disaster-co-occurrence
    # guard now suppresses WEATHER_INFO when a flood/preparation token is
    # also present, so we can now include "monsoon" without hijacking.
    pred = classifier.classify(
        "can you tell me about flood preparedness in karachi during monsoon"
    )
    assert pred.method != "rule_short_query"
    assert pred.intent == IntentTypes.SAFETY_ADVICE
    assert pred.sub_intent == "flood"


# ─── Phase 5a.1 Issue 2: monsoon / weather over-fire fix ────────────────────
# Locked decisions:
#   - Genuine weather-data queries STILL fire WEATHER_INFO ("weather forecast
#     karachi", "is it raining today").
#   - Queries that pair a weather keyword with a disaster / preparation token
#     route to SAFETY_ADVICE (with the disaster sub_intent), NOT WEATHER_INFO.
#     The user wants flood-prep guidance, not "I don't have real-time data".
@pytest.mark.parametrize(
    "query,expected_intent,expected_sub",
    [
        ("weather forecast karachi", IntentTypes.WEATHER_INFO, None),
        ("is it raining today", IntentTypes.WEATHER_INFO, None),
        (
            "I am planning a trip to Karachi during monsoon, "
            "what flood risks should I prepare for",
            IntentTypes.SAFETY_ADVICE,
            "flood",
        ),
        ("monsoon flooding preparation", IntentTypes.SAFETY_ADVICE, "flood"),
    ],
    ids=lambda v: str(v)[:50],
)
def test_weather_vs_safety_routing(classifier, query, expected_intent, expected_sub):
    pred = classifier.classify(query)
    assert pred.intent == expected_intent, (
        f"query={query!r}: expected {expected_intent}, got {pred.intent} "
        f"(method={pred.method}, conf={pred.confidence:.2f})"
    )
    if expected_sub is not None:
        assert pred.sub_intent == expected_sub, (
            f"query={query!r}: expected sub_intent={expected_sub}, "
            f"got {pred.sub_intent}"
        )
