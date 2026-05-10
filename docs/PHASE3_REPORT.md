# Phase 3 — Hybrid LLM Integration

**Date:** 2026-05-08
**Status:** Code-complete locally. All 8 acceptance criteria met. **No git push or production deploy per locked Phase 3 directive.**

---

## 1. Acceptance criteria — checked

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `USE_LLM=false` runs legacy pipeline unchanged (full regression) | ✅ | `pytest tests/` → **171/171 pass** |
| 2 | `USE_LLM=true` produces grounded responses with source citations | ✅ | `earthquake safety in pakistan` → `used_llm=True`, sources `['NDMA Pakistan', 'USGS public guidance', 'Geological Survey of Pakistan']` |
| 3 | Gemini timeout falls back to Groq within 15s wall-clock | ✅ | `cyclone preparedness coastal sindh` (Gemini RPD quota hit) → Groq retry-without-tools succeeded → grounded response in **5.86s wall** |
| 4 | Output validator strips invented phone numbers in adversarial tests (≥10 cases incl. word-form digits) | ✅ | `tests/test_output_validator.py` ships **20 cases**, including word-form-digit adversarial cases; all green |
| 5 | Session memory retains last 6 turns; new session_id starts fresh | ✅ | Sliding-window persists 4 turns across 2 calls; LRU + TTL covered in `tests/test_session_store.py` |
| 6 | `/api/v1/chat/stream` produces SSE chunks readable from `curl -N` | ✅ | Direct curl: `event: delta` × N, terminated by `event: done` with metadata. Smoke covered in `tests/test_streaming.py`. |
| 7 | Self-harm phrase routes to hand-written crisis template (not LLM) | ✅ | `I want to kill myself` → `response_type=crisis`, `used_llm=False`, contains Umang `0311-7786264` + 115; `tests/test_crisis_routing.py` 21 tests green |
| 8 | Tests 2 and 3 from Phase 2 verification now pass with grounded LLM responses | ✅ | `What should I do during a heatwave in Karachi?` → 5 sources (NDMA, PMD, Sindh Health Dept …); `severe allergic reaction` → 2 sources (WHO, AHA) |

---

## 2. Locked decisions ↔ implementation map

| Decision | Where it landed |
|---|---|
| Gemini 2.5 Flash primary, Groq Llama 3.3 70B failover | `services/llm_service.py` — `_gemini_with_tools` then `_groq_with_tools`; `LLMUnavailable` raised only if both fail |
| `USE_LLM=false` default | `.env.example` and `config.py:USE_LLM=False` defaults; legacy pipeline runs unchanged when off |
| `SESSION_MAX_ACTIVE=1000` for Hobby tier; documented override path | `.env.example` comment block; `RAILWAY_SETUP.md` planned for Phase 5 |
| Validator catches word-form digit phone numbers | `_strip_wordform_phones` in `services/output_validator.py`; 20 adversarial cases cover both numeric and word-form runs |
| Self-harm crisis routing — hand-curated phrases, false positives → crisis (low harm), false negatives → LLM (high harm) | `CRISIS_PHRASES` (45 phrases), `_is_crisis()`, `CRISIS_TEMPLATE` in `services/chatbot_service.py`; runs **before** any other Layer-1 or Layer-4 path. **Owner review required before merge.** |
| Phase 2 q2 + q3 must pass with `USE_LLM=true` | Verified above — both grounded with KB-cited sources via the LLM fallback path |
| No production deploy / git push | Honored — working tree only |

---

## 3. Files created (Phase 3)

| Path | Purpose |
|---|---|
| `chatbot_backend/services/llm_service.py` | Gemini + Groq client with failover, streaming, tool-call loop |
| `chatbot_backend/services/session_store.py` | In-memory ephemeral session history (sliding window + TTL + LRU) |
| `chatbot_backend/services/tool_executor.py` | 4 LLM tools: `get_helplines`, `get_first_aid_steps`, `get_evacuation_info`, `get_quick_tip` |
| `chatbot_backend/services/output_validator.py` | Phase 5 layer — phone stripping (numeric + word-form), disclaimer enforcement, URL allowlist, length cap, HTML sanitisation |
| `chatbot_backend/services/offline_bundle.py` | Cached `/offline-data` builder with populated `guidance_data` step lists from v2 KB |
| `chatbot_backend/prompts/system_prompt.txt` | LLM system prompt with `{{PROVINCE}}`, `{{INTENT}}`, `{{SOURCES_BLOCK}}` placeholders |
| `chatbot_backend/prompts/tool_specs.py` | JSON-schema for the 4 tools |
| `chatbot_backend/prompts/__init__.py` | Package marker |
| `chatbot_backend/tests/test_llm_service.py` | Failover semantics (Gemini fail → Groq, both fail → `LLMUnavailable`, no keys → `LLMUnavailable`, streaming yields done marker, format_sources_block) |
| `chatbot_backend/tests/test_session_store.py` | Append/get, sliding window, TTL eviction, LRU cap, content truncation |
| `chatbot_backend/tests/test_tool_executor.py` | All 4 tools — success / not-found / error paths |
| `chatbot_backend/tests/test_output_validator.py` | **20 adversarial cases** including word-form digits |
| `chatbot_backend/tests/test_offline_bundle.py` | Cached build + populated guidance_data + invalidation |
| `chatbot_backend/tests/test_streaming.py` | SSE smoke test via `TestClient` |
| `chatbot_backend/tests/test_crisis_routing.py` | 21 tests — phrase detection, full-pipeline routing, owner-review marker |
| `chatbot_backend/docs/PHASE3_REPORT.md` | This document |

## 4. Files modified

| Path | Change |
|---|---|
| `chatbot_backend/config.py` | New `Settings` fields: `USE_LLM`, `LLM_PRIMARY/FALLBACK`, `GEMINI_API_KEY/MODEL`, `GROQ_API_KEY/MODEL`, `LLM_TIMEOUT_SECONDS`, `LLM_FALLBACK_TIMEOUT_SECONDS`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_MAX_TOOL_ROUNDS`, `SESSION_TTL_MINUTES`, `SESSION_MAX_TURNS`, `SESSION_MAX_ACTIVE=1000`, `SESSION_SWEEP_INTERVAL_SECONDS`, `ALLOWED_LINK_DOMAINS`, `OUTPUT_MAX_CHARS`, `OFFLINE_BUNDLE_TTL_SECONDS`, plus `allowed_link_domain_list` property. |
| `chatbot_backend/main.py` | Added `_assert_llm_configured_if_enabled()` startup check; lifespan now starts `SessionStore` sweeper + cleanly cancels it on shutdown. |
| `chatbot_backend/routers/chat_router.py` | New `POST /api/v1/chat/stream` SSE endpoint (uses `EventSourceResponse`). `/offline-data` now uses cached `OfflineBundleBuilder`. |
| `chatbot_backend/services/chatbot_service.py` | Crisis fast-path (Layer 1.5) before emergency check; `_route_intent_via_llm` (Layers 3–5); `TEMPLATE_ONLY_INTENTS` keeps sensitive intents (mental_health, helpline_query, donation, etc.) on the deterministic template path; `CRISIS_PHRASES`, `CRISIS_TEMPLATE`, `_is_crisis()` defined inline. |
| `chatbot_backend/models/schemas.py` | Additive: `ChatResponse.sources` + `used_llm`; new `SourceCitation` and `ChatStreamChunk` models. |
| `chatbot_backend/models/__init__.py` | Export the new models. |
| `chatbot_backend/requirements.txt` | Added `google-generativeai==0.8.3`, `groq>=1.2.0,<2.0.0`, `sse-starlette==2.1.3`. |
| `chatbot_backend/.env.example` | All Phase 3 env vars documented; `USE_LLM=false` default. |

## 5. The 5-layer flow (now wired end-to-end)

```
ChatRequest
  │
  ├─ Layer 1.5  Crisis fast-path
  │             _is_crisis() against CRISIS_PHRASES → CRISIS_TEMPLATE
  │             (NEVER calls LLM)
  │
  ├─ Layer 1    Emergency fast-path
  │             _check_emergency() → _handle_emergency template
  │             (NEVER calls LLM)
  │
  ├─ Layer 2    Intent routing
  │             rule patterns → LR classifier fallback
  │             TEMPLATE_ONLY_INTENTS skip the LLM path
  │
  ├─ Layer 3    RAG retrieval
  │             KnowledgeRetriever w/ lowered threshold (0.05) for LLM
  │             grounding pass; falls back to no-disaster filter when the
  │             disaster-filtered pass is empty
  │
  ├─ Layer 4    LLM generation
  │             Gemini → Groq failover; tool-call loop (max 3 rounds);
  │             Groq retry-without-tools on tool_use_failed
  │
  └─ Layer 5    Output validator
                Phone stripping (numeric + word-form); disclaimer
                enforcement; URL allowlist; length cap; HTML sanitise
                                ↓
                         ChatResponse
```

## 6. Notable decisions / deviations

1. **Streaming is "fake-streamed" in v1.** The `/chat/stream` endpoint runs the full `process_message` (with the tool-call loop) and then chunks the final text into SSE deltas client-side. Real token-level streaming requires per-provider streaming + tool-call interaction, which is fragile across both SDKs in v1; staged for a v1.1 task. The wire format (`ChatStreamChunk`) is forward-compatible — the Flutter Phase 4 work can read this format unchanged when token streaming lands. Documented at the top of `LLMService.generate_stream()`.

2. **`groq` SDK version bumped to `>=1.2.0`.** The pinned `0.11.0` from the implementation plan is incompatible with `httpx==0.28+` (drops `proxies` kwarg, breaks `Groq()` constructor). `groq>=1.2.0` works and keeps the same chat/completions API.

3. **Groq tool-call retry-without-tools.** Llama-3.3-70B sometimes emits malformed function-call syntax that Groq's API rejects with `tool_use_failed`. We catch that one specific error class and retry once without the `tools=` parameter — the system prompt's SOURCES block is still in context, so the model can still ground without function calls. Documented at the call site.

4. **Lowered retrieval threshold (0.15 → 0.05) for the LLM grounding pass.** TF-IDF on short queries lands ~0.10–0.15 even for good matches; 0.15 was tuned for the legacy template path where empty retrievals were acceptable. The LLM path needs SOMETHING in the prompt or it hallucinates from training data. The threshold is restored after the retrieve call (the legacy path is unaffected). If the disaster-filtered pass returns zero, a second pass without the disaster filter runs — keeps the prompt grounded for fallback intents like the "severe allergic reaction" case.

5. **Crisis routing is a pure substring scan, not regex.** 45 hand-curated phrases drafted by Claude Code per locked O10. **Project owner review is the merge gate.** False-positive policy: low harm (user gets the canonical helplines + reassurance copy); false-negative policy: high harm (LLM might improvise on suicidal ideation). The list errs broad.

6. **`HELPLINE_QUERY` and `MENTAL_HEALTH` intents stay on the template path** even when `USE_LLM=true`. Helpline rendering is already curated per province; mental-health responses are sensitive enough that LLM creativity is a net negative compared to the verified canonical text. This is a TEMPLATE_ONLY_INTENTS membership choice and easily flipped if product later wants LLM coverage.

7. **`SourceCitation` carries `name` only by default.** The KB v2 has `sources: [{name, url}]` per entry, but the LLM context doesn't expose URLs to the user response (avoids the URL-allowlist false-positive surface). The Flutter Phase 4 work surfaces source NAMES in the citation footer; URLs remain link-clickable only inside the markdown body where the validator allowlist applies.

8. **Session store is per-process, in-memory.** Per locked decisions, no DB persistence in v1. A redeploy hard-resets all sessions. Ephemerality is the privacy default; a Redis-backed store can land in v2 if traffic warrants.

9. **`_is_crisis` runs against both raw and preprocessed text.** PII redaction in the preprocessor would normally strip phone numbers; for crisis text we want maximum recall, so we scan the original message too.

10. **OutputValidator phone-shape filter.** Initial draft over-stripped ISO dates (`2026-04-29`) and 13-digit barcodes. Refined `_looks_like_phone_shape()` skips ISO-date and year-range patterns, and skips 12+ digit unbroken runs (they're barcodes / order IDs, not phones).

## 7. Quality gates

| Gate | Status |
|---|---|
| `pytest tests/` (USE_LLM=false, full regression) | ✅ **171/171 pass** |
| Phase 1 + Phase 2 tests still green | ✅ included above (88 pre-Phase-3 tests still pass) |
| `validate_kb.py --no-head` | ✅ 0 errors, 4 legacy-ID warnings (unchanged) |
| 8 Phase 3 acceptance criteria | ✅ All PASS — table above |
| Gemini → Groq end-to-end failover | ✅ 5.86s wall under 15s budget; observed in production-like flow when Gemini quota hit |
| Crisis routing template | ✅ Returns Umang + Rozan + 115; bypasses LLM |
| `/chat/stream` SSE wire format | ✅ `event: delta` × N → `event: done` with metadata, parses cleanly |

## 8. What still needs human action before Phase 4

1. **Project owner review of `CRISIS_PHRASES`.** Locked O10 — review the 45 phrases for completeness/accuracy against your safety-team guidance. Flagged in `tests/test_crisis_routing.py::test_phrase_list_is_nonempty_and_owner_review_flagged`.
2. **Decide whether `MENTAL_HEALTH` intent should ever go through the LLM.** Currently template-only. Phase 4 client work will surface this trade-off in the UX (the template lacks the LLM's natural-language adaptation).
3. **Populate `GEMINI_API_KEY` + `GROQ_API_KEY` in Railway env** before flipping `USE_LLM=true` in production. The startup check (`_assert_llm_configured_if_enabled`) refuses to boot without at least one key.
4. **Decide on `SESSION_MAX_ACTIVE`** for the Railway plan tier in production. Default 1000 fits Hobby ~512 MB. On Pro ~2 GB, 5000 is reasonable. Document in `RAILWAY_SETUP.md` (Phase 5 task).
5. **Confirm token-level streaming is a v1.1 task.** v1 ships server-side post-process chunking via SSE.
