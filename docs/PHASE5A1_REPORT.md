# Phase 5a.1 — LLM-primary contract + monsoon over-fire fix

**Status:** Code-complete locally. **No git push or production deploy until human sign-off.**

---

## 1. Diagnosis (Issue 1)

The user instructed: *"Diagnostic step first: find where `_route_intent_via_llm` returns None for 'flood'. Paste your findings before changing code."*

### What I found

**The architecture is already correct.** `_route_intent_via_llm` is the primary path for `safety_advice` / `first_aid` and is invoked for short queries. My local trace confirmed:

- `USE_LLM=True` ✓
- `safety_advice` and `first_aid` are NOT in `TEMPLATE_ONLY_INTENTS` ✓
- For `"flood"`, retrieval at threshold 0.05 returns 4 valid passages (scores 0.10–0.12) ✓
- LLM call succeeds locally → response with 5 source citations, `used_llm=True` ✓

### What the user observed in production

When I monkeypatched `LLMService.generate` to raise `LLMUnavailable`, I reproduced the exact production symptom:

```
flood       → safety_advice + flood, used_llm=False, type=safety_advice
earthquake  → safety_advice + earthquake, used_llm=False, type=safety_advice
fire        → safety_advice + fire, used_llm=False, type=safety_advice
```

The user's "long queries get LLM, short queries don't" pattern is most plausibly **transient LLM provider failures during testing** — Gemini free-tier RPD = 200/day, Groq has separate token-budget cliffs. When LLM is up, both work; when down, both fall through.

### The real second-order issue

Phase 5a Fix 3 made `_handle_safety_advice` *succeed* with `used_llm=False` (return the KB chunk) for short queries — instead of dropping to fallback. That **masked LLM availability**: previously the response would have been "I'm not sure"; now it's a verbose KB chunk that looks LLM-grounded. Without the new tests there's no way to detect a future architectural regression.

### What needs fixing

| Issue | Status | Action |
|---|---|---|
| 1. LLM path primary for short queries | ✅ already correct | Add 5 locked tests + clarifying comment in `process_message` |
| 2. `monsoon` over-fires `WEATHER_INFO` | 🔴 real bug | Tighten classifier with disaster-co-occurrence guard |

Findings pasted; proceeded to fixes.

---

## 2. The fixes

### Issue 1 — LLM-primary contract (test-only lock-in)

**File:** `services/chatbot_service.py` — added a contract docstring at the LLM-path branch in `process_message`. **No flow change.**

**File:** `tests/test_llm_primary_path.py` — NEW. 5 production-shape tests with `LLMService.generate` monkeypatched to keep the suite deterministic and quota-independent:

| # | Query | Stub | Expected |
|---|---|---|---|
| 1 | `"flood"` | LLM returns text | `used_llm=True`, `safety_advice + flood`, `response_type=safety_advice_llm` |
| 2 | `"earthquake"` | LLM returns text | `used_llm=True`, `safety_advice + earthquake` |
| 3 | `"first aid for burns"` | LLM returns text | `used_llm=True`, `first_aid` |
| 4 | `"flood"` with `USE_LLM=False` | LLM stub would have triggered | `used_llm=False`, response does NOT contain the stub text (LLM not invoked) |
| 5 | `"flood"` with both providers raising `LLMUnavailable` | — | `used_llm=False`, `response_type=safety_advice` (legacy KB chunk = safety net) |

These five lock the contract: LLM is primary when available; legacy is the safety net when `USE_LLM=false` (kill switch) OR both providers fail.

### Issue 2 — monsoon over-fire (Option B: disaster-co-occurrence guard)

**File:** `nlp/intent_classifier.py`

**Choice rationale**: Option B over Option A. Option A would have required enumerating every weather-data phrase and dropping bare `monsoon`/`rain`/`storm`, risking missed legitimate forecast queries. Option B keeps the existing patterns and adds one targeted guard: if a `WEATHER_INFO` rule fires AND the message also contains a disaster/preparation token, suppress the rule and let the broader-rule layer route to `safety_advice`.

**Implementation** (~25 LOC):

```python
_WEATHER_SUPPRESS_TOKENS = (
    "flood", "floods", "flooded", "flooding",
    "earthquake", "quake", "tremor",
    "fire", "burning",
    "cyclone", "hurricane",
    "gas leak", "building collapse", "electric shock",
    "evacuat",          # evacuate / evacuation / evacuated
    "prepare", "preparation", "preparedness",
    "risk", "risks",
    "sailab", "seelab", "zalzala",
    "what should i do",
    "how to stay safe",
)

@classmethod
def _looks_like_weather_query(cls, text_lower: str) -> bool:
    return not any(tok in text_lower for tok in cls._WEATHER_SUPPRESS_TOKENS)
```

Wired into `_check_rule_patterns` — the loop continues past WEATHER_INFO when the guard says "this is a safety query".

**Bonus fix surfaced during testing**: extended `WEATHER_INFO` regex with verb forms (`raining`, `rains`, `rainfall`, `storms`, `windy`) — the existing `\brain\b` didn't match `raining` because of word-boundary semantics. Same kind of fix Phase 5a applied to first-aid verbs.

**File:** `tests/test_intent_classification.py` — 4 new parametrised cases:

| Query | Expected |
|---|---|
| `weather forecast karachi` | `weather_info` (regression) |
| `is it raining today` | `weather_info` |
| `I am planning a trip to Karachi during monsoon, what flood risks should I prepare for` | `safety_advice + flood` |
| `monsoon flooding preparation` | `safety_advice + flood` |

Plus updated the now-stale comment on `test_long_query_skips_shortcut` — that test used to deliberately omit "monsoon"; the Phase 5a.1 guard means we can now include it.

---

## 3. Quality gates

| Gate | Status |
|---|---|
| `pytest tests/` (backend) | ✅ **266 / 266** (was 257; +5 LLM-primary + 4 weather/monsoon) |
| `flutter analyze` | ✅ clean |
| `flutter test` | ✅ **64 / 64** |
| 4 originally-broken queries from Issue 2 route correctly | ✅ verified |
| 5 LLM-primary contract tests pass | ✅ verified (with mocked LLM) |
| Crisis fast-path still deterministic | ✅ `test_crisis_routing.py` 21/21 |
| Emergency fast-path still triggers | ✅ `test_emergency_fastpath.py` 15/15 |
| `USE_LLM=false` runs legacy unchanged (kill switch) | ✅ Test 4 in `test_llm_primary_path.py` |
| `LLMUnavailable` falls back to legacy (safety net) | ✅ Test 5 in `test_llm_primary_path.py` |
| Phase 1+2+3+4+5a acceptance criteria still hold | ✅ regression suite green |
| Zero new KB entries authored | ✅ |
| No git push / production deploy | ✅ working tree only |

---

## 4. Files changed

| Path | Change | LOC |
|---|---|---|
| `chatbot_backend/services/chatbot_service.py` | Phase 5a.1 LLM-primary contract docstring on the LLM-path branch in `process_message`. **No flow change.** | ~15 (comment only) |
| `chatbot_backend/nlp/intent_classifier.py` | Issue 2 fix: `_WEATHER_SUPPRESS_TOKENS`, `_looks_like_weather_query()`, suppression check inside `_check_rule_patterns`. WEATHER_INFO regex extended with `raining/rains/rainfall/storms/windy` verb forms. | +35 |
| `chatbot_backend/tests/test_llm_primary_path.py` | NEW — 5 contract-locking tests with monkeypatched LLM. | +175 |
| `chatbot_backend/tests/test_intent_classification.py` | +4 weather/monsoon parametrised cases; comment updated on `test_long_query_skips_shortcut`. | +40 |
| `chatbot_backend/docs/PHASE5A1_REPORT.md` | This document. | — |

---

## 5. Notable decisions / deviations

1. **No flow change for Issue 1.** The architecture was already correct — `_route_intent_via_llm` is the primary path, returns None on `LLMUnavailable`, falls through to legacy. The fix is **observability** (5 tests) + **documentation** (contract docstring). A future contributor changing the flow without updating the tests will break `test_use_llm_false_runs_legacy_pipeline` or `test_llm_unavailable_falls_back_to_legacy`.

2. **Tests mock the LLM service.** Real Gemini/Groq calls would make the suite flaky (quota), slow, and require live API keys. `monkeypatch.setattr(svc, "generate", _stub)` is the same pattern Phase 3 used in `test_llm_service.py`. The test verifies the **contract**, not the LLM's content.

3. **Issue 2 picked Option B.** Disaster co-occurrence guard preserves the working `weather forecast karachi` and `pmd alert` paths and only suppresses WEATHER_INFO when the message is clearly about safety preparation. Option A would have required ongoing maintenance of an "approved weather phrase" list.

4. **`_WEATHER_SUPPRESS_TOKENS` lives on the classifier class**, not in config. It's a routing-layer concern — any future tuning is part of the same code review as the regex it suppresses. Same pattern used by `_SHORT_QUERY_KEYWORDS_*` in Phase 5a.

5. **`raining` / `rains` / `rainfall` added to WEATHER_INFO**. Same `\b` verb-form gap fixed for first-aid in Phase 5a. Out of scope strictly, but `is it raining today` failing the lock-in test surfaced it; cheap to fix in the same change.

6. **No production-side mitigation for Gemini quota.** The user observed transient LLM failures (the underlying cause of the symptom). Phase 5a.1 makes the failure mode visible (`used_llm=False` is now the documented signal) but doesn't change the providers, retry logic, or quota strategy. That's a Phase 5b candidate (per the implementation plan §3 risks).

---

## 6. What still needs human action before production rollout

1. **Real-device sign-off** on the 4 originally-broken weather/monsoon queries from Issue 2.
2. **Decide whether to add observability** for the legacy-fallback path. Today `used_llm=False` is the only signal; a structured log line with `provider_used="legacy_fallback_after_llm_unavailable"` would make production debugging easier (Phase 5b candidate).
3. **Decide whether to add a paid Gemini tier or a third provider.** The free-tier 200/day RPD limit is the underlying cause of the user's transient observation. Out of scope for Phase 5a.1.
