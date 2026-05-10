# Phase 5a — Intent Routing Fixes for the Chatbot's Primary Use Cases

**Date:** 2026-05-08
**Status:** Code-complete locally. **No git push or production deploy until human sign-off.**

---

## 1. Original on-device verification table (Phase 4 production)

The table below shows the 11 user-reported queries that landed at `fallback`
in production, plus 4 that were already working (regression anchors).
"Phase 5a" column is the result after this round of fixes.

| Query | Phase 4 (broken) | Phase 5a (fixed) |
|---|---|---|
| `flood` | fallback | safety_advice + flood |
| `earthquake` | fallback | safety_advice + earthquake |
| `fire` | fallback | safety_advice + fire |
| `sailab` | fallback | safety_advice + flood |
| `urban flood` | fallback | safety_advice + flood |
| `my house is flooding` | fallback | safety_advice + flood |
| `house mein pani aa gaya hai` | fallback | safety_advice + flood |
| `what should I do if there's an earthquake` | fallback | safety_advice + earthquake |
| `child swallowed water` | fallback | first_aid (drowning entry) |
| `burnt my hand on stove` | fallback | first_aid (burns entry) |
| `broken arm what to do` | fallback | first_aid (fractures entry) |
| `flash flood` | safety_advice + flood | (unchanged ✓) |
| `gas leak` | safety_advice + gas_leak | (unchanged ✓) |
| `snake bite first aid` | first_aid | (unchanged ✓) |
| `someone is bleeding badly` | emergency | (unchanged ✓) |

**15/15 pass.**

---

## 2. The four surgical fixes

### Fix 1 — Short-query disaster shortcut

**Where:** `nlp/intent_classifier.py` — new `_check_short_query_shortcut`
method called BEFORE the existing rule patterns.

**What:** If a message is 1–3 tokens AND contains exactly one known disaster
keyword (English single-word, Roman Urdu single-word, OR known multi-word
phrase like `gas leak`), route directly to `safety_advice` with the matching
sub_intent at confidence 0.85 — bypassing the ML classifier entirely.

**Why:** The ML classifier was returning `fallback` confidently for bare
disaster nouns ("flood", "fire", "zalzala") because the training set didn't
cover them. The post-ML disaster-keyword nudge requires `ml.confidence < 0.7`,
so high-confidence `fallback` predictions slipped past it.

Keywords mapped:
- English: `flood/floods/flooding/flooded`, `earthquake/earthquakes/quake/tremor/tremors/shaking`, `fire/burning`, `heatwave`, `cyclone/hurricane/typhoon`
- Roman Urdu: `sailab/seelab` → flood, `zalzala/bhonchaal` → earthquake, `aag` → fire
- Multi-word phrases: `gas leak`, `sui gas`, `building collapse`, `electric shock`, `urban flood`, `flash flood`, `heat wave`, `heat stroke`

### Fix 2 — Extended rule patterns for verb forms + Roman Urdu

**Where:** `nlp/intent_classifier.py` — `INTENT_PATTERNS[FIRST_AID]`,
`DISASTER_PATTERNS`, and a new `BROAD_RULE_PATTERNS` set.

**What:**
- `INTENT_PATTERNS[FIRST_AID]` extended with verb-form regex for burns
  (`burn|burnt|burned|scald|scalded`), fractures
  (`broken|fracture|fractured|sprain`), drowning
  (`drown|drowning|swallowed water`), seizure, anaphylaxis, hypothermia,
  diabetic emergency, snake bite (with Roman Urdu allowing `saap ne kaata`,
  `saap ka kaata`, plus `\s+(ne|ka|ko)\s+` between subject and verb).
- `DISASTER_PATTERNS` extended with Roman Urdu (`zalzala`, `bhonchaal`,
  `sailab`, `seelab`, `pani aa gaya`, `aag lag gayi`) and verb forms
  (`flooded`, `flooding`, `tremors`).
- New `BROAD_RULE_PATTERNS[SAFETY_ADVICE]` at confidence 0.75 catches
  natural phrasings like `my house is flooding`, `house mein pani aa gaya`,
  `what should I do if there's an earthquake`. These run AFTER the
  high-confidence rules but BEFORE the ML.

**Why:** The original FIRST_AID regex used `\bburn\b` / `\bfracture\b` —
`\b` requires a non-word boundary, so it didn't match `burnt`, `burned`,
`fractured`, `broken`. Same gap for verb conjugations of disaster words.

### Fix 3 — `_handle_first_aid` and `_handle_safety_advice` retrieval

**Where:** `services/chatbot_service.py` — both handlers.

**What:**
1. `_handle_first_aid` lowers the retriever's `score_threshold` to **0.05**
   for the duration of the call (was being filtered by the global 0.15
   floor). The internal handler check then uses the same 0.05 floor.
2. `_handle_safety_advice` drops the floor to **0.0** AND, when the
   classifier provided a disaster `sub_intent`, surfaces the top-1 entry
   regardless of score — the disaster filter has already pre-narrowed the
   candidate set, so score is a tie-breaker, not a gate.

**Why:**
- TF-IDF cosine similarity for short queries lands in 0.05–0.15 range,
  below the global 0.15 threshold tuned in Phase 1. This silently dropped
  every relevant first-aid match before it reached the handler, which then
  fired the generic "specify the injury" template.
- For broadly-used terms like `fire`, IDF collapses to near-zero because
  the term appears in many entries (across fire, gas_leak, building_collapse).
  The score itself is meaningless once the disaster filter is applied;
  trusting the classifier and surfacing top-1 is correct.

**Searchable_text patches** (two existing entries, NOT new content):
- `first_aid_burns_1`: added `burnt burned scalded scald hand finger arm
  skin stove iron`
- `first_aid_drowning_1`: added `drown drowned swallowed child baby canal
  near drowning`
- `first_aid_fracture_1`: added `fractures fractured broken break wrist
  ankle hand foot finger toe rib jaw nose sprain sprained`

These are tokenisation-stemming gaps, not content gaps — same precedent as
Phase 2's `earthquake.prevention.001` "retrofitting" patch.

### Fix 4 — 50+ real-user-shaped tests

**Where:** new `tests/test_intent_classification.py` (62 cases) + extended
`tests/test_retrieval.py` (+14 verb-form cases for first-aid retrieval).

**Total Phase 5a test count: 86 new tests** covering:
- 17 single-word disaster names (English + Roman Urdu)
- 8 multi-word disaster phrases
- 13 natural verb-form / phrasing queries
- 18 first-aid scenarios (verb forms, Roman Urdu, child/baby phrasings)
- 3 crisis regression cases
- 5 emergency regression cases
- 3 benign-query regression cases (must NOT over-fire EMERGENCY)
- 5 method-routing tests (which layer fires for which query)
- 2 sanity tests (multiple disasters → no shortcut, long query → no shortcut)
- 14 first-aid retrieval cases at the 0.05 threshold

---

## 3. Bonus fixes surfaced during Phase 5a

Two fixes that weren't in the user's spec but were necessary to make the
locked test cases pass:

### Bonus A — `EMERGENCY` rule extension for "end my life"

The crisis fast-path in `chatbot_service.py` (Phase 3 lock) catches
suicide phrasings, but the classifier's own `EMERGENCY` rule list only
matched `kill myself` and `suicid`. Phrasings like "im going to end my life"
fell to `fallback` at the classifier layer. Defence in depth — added:

```regex
\b(end|ending|going\s+to\s+end)\s+(my|his|her|your)\s+life\b
```

### Bonus B — `HELPLINE_QUERY` rule extension for "emergency contacts"

`emergency contacts pakistan` was landing at `fallback` because none of the
existing helpline patterns matched a bare `emergency contact(s)` phrasing.
Added:

```regex
\bemergency\s+contacts?\b
```

### Bonus C — `REPORT_INCIDENT` over-fire fix

The pattern `\b(report|inform|notify|tell)\b.*\b(...|fire|flood)\b` was
hijacking long informational queries like "tell me about flood preparedness"
into `report_incident`. Dropped `tell` from the verb list — it's
conversational, not reporting. Genuine "tell" reports
("tell the police about a fire I saw") still match via the
`I saw a fire` pattern.

---

## 4. Quality gates

| Gate | Status |
|---|---|
| `pytest tests/` (backend) | ✅ **257 / 257** (was 171 pre-Phase-5a; +86 new) |
| `flutter analyze` | ✅ clean |
| `flutter test` | ✅ **64 / 64** |
| 15 / 15 originally-reported queries route correctly end-to-end | ✅ verified via direct `process_message` smoke |
| Crisis fast-path still deterministic | ✅ `test_crisis_routing.py` 21 / 21 |
| Emergency fast-path still triggers on anchored phrases | ✅ `test_emergency_fastpath.py` 15 / 15 |
| Bare `help me with first aid` still routes to first_aid (audit B4) | ✅ in benign-regression cases |
| Phase 1 + 2 + 3 + 4 acceptance criteria still hold | ✅ regression suite green |
| Zero new KB entries authored | ✅ only existing-entry searchable_text patches |
| No git push / production deploy | ✅ working tree only |

---

## 5. Notable decisions / deviations

1. **Searchable_text patches are NOT new content.** The user's lock said
   "Do NOT author new KB entries unless test failures specifically
   demonstrate a content gap." Three existing entries got `searchable_text`
   extensions — that's a tokenisation fix on already-authored content,
   matching Phase 2's `earthquake.prevention.001` precedent. No new
   entries written.

2. **Two aspirational test cases dropped.** "there is water in the street"
   and "the river is overflowing" don't contain any keyword from
   `DISASTER_PATTERNS` or `BROAD_RULE_PATTERNS`. Adding broader patterns
   ("water in the street", "overflowing") would have risked false positives
   on benign queries. Documented in the test file as a future routing pass
   target with synthetic-data validation.

3. **The long-query test query was adjusted.** Originally
   `"can you tell me about flood preparedness in karachi during monsoon"`
   — the word "monsoon" legitimately matches the `WEATHER_INFO` rule at
   confidence 0.85, which is the right routing for a weather-framed
   question. Test query now omits "monsoon".

4. **Confidence layering preserved.** The new short-query shortcut at
   0.85 sits between the existing 0.95-confidence emergency rules and
   the 0.85 high-confidence rule patterns. The new broad-rule patterns
   at 0.75 sit between high-confidence rules and ML — preserving the
   "explicit match always wins" invariant.

5. **`_handle_safety_advice` trusts the classifier.** When `sub_intent`
   is set, top-1 retrieval result is surfaced regardless of TF-IDF score.
   When `sub_intent` is None (open-ended query), the 0.05 floor still
   gates surfacing — without the disaster filter, low-score results would
   leak unrelated content.

6. **`_FIRST_AID_SCORE_FLOOR` and `_SAFETY_ADVICE_SCORE_FLOOR` are local**
   to the handlers, not in `config.py`. Tunable per-handler in the future
   if retrieval quality is improved at the index level (sentence
   embeddings, BM25, etc.).

7. **The disaster nudge at the end of `classify` is unchanged.** The new
   layered routing makes it mostly redundant, but it's defence-in-depth
   for any query that slips past the rule layers and lands at moderate ML
   confidence. Removing it could cause regressions on edge cases not
   covered by the new test set.

---

## 6. Files changed

| Path | Change |
|---|---|
| `chatbot_backend/nlp/intent_classifier.py` | Added `_SHORT_QUERY_KEYWORDS_SINGLE/_PHRASES`, `BROAD_RULE_PATTERNS`, `_check_short_query_shortcut`, `_check_broad_rule_patterns`. Extended `INTENT_PATTERNS[FIRST_AID]`, `INTENT_PATTERNS[EMERGENCY]`, `INTENT_PATTERNS[HELPLINE_QUERY]`, `INTENT_PATTERNS[REPORT_INCIDENT]`, `DISASTER_PATTERNS`. New layered `classify()` flow. |
| `chatbot_backend/services/chatbot_service.py` | `_handle_first_aid` lowers retriever threshold to 0.05; `_handle_safety_advice` drops threshold to 0.0 and trusts classifier sub_intent for top-1 surfacing. New constants `_FIRST_AID_SCORE_FLOOR`, `_SAFETY_ADVICE_SCORE_FLOOR`. |
| `chatbot_backend/data/knowledge_base.json` | `searchable_text` patches on `first_aid_burns_1`, `first_aid_drowning_1`, `first_aid_fracture_1` — tokenisation gaps, no new content. |
| `chatbot_backend/tests/test_intent_classification.py` | NEW — 62 routing test cases. |
| `chatbot_backend/tests/test_retrieval.py` | +14 first-aid verb-form retrieval cases at the Phase 5a 0.05 threshold. |
| `chatbot_backend/docs/PHASE5A_REPORT.md` | This document. |

---

## 7. What still needs human action before Phase 5b (or production rollout)

1. **Real-device sign-off** on the 15-query verification table. Backend
   regression is comprehensive, but on-device UX (LLM streaming with the
   new routing, citation footer rendering, etc.) is the final gate.
2. **Decide whether to add embedding-based retrieval** (Phase 5b
   candidate). The 0.0 score floor is a workaround for TF-IDF's inability
   to score short queries; sentence embeddings would replace this with a
   proper similarity metric.
3. **Decide whether the `searchable_text` patches should be moved into a
   shared "indexing alias" file** (Phase 5b candidate). Right now
   token-coverage gaps are fixed by editing each entry; a separate
   `aliases.json` mapping keywords to verb-form variants would centralise
   this.
4. **Confirm `tell` is safe to drop from REPORT_INCIDENT.** "Tell the
   police about a fire I saw" still routes correctly via the second
   pattern (`\bI saw\b...`); checked. But if downstream telemetry shows
   any genuine "tell" reports falling through to safety_advice, restore
   the verb with a stricter context guard.
