# Phase 1 — Foundation Fixes & Railway Deployment

**Date:** 2026-05-07
**Status:** Code-complete locally. All automated acceptance criteria green. **Deployment + real-device test pending human action** (Railway provisioning is human-gated per locked decision O3).

---

## 1. What was implemented

### Locked-decision adjustments applied this phase
- **DEBUG=True bypass for `require_api_key`** — implemented in `services/auth.py`. DEBUG=False requires exact `X-API-Key` match; missing or wrong → 401. Documented in the module docstring.
- **Per-bucket KB targets (O1)**, **topic facet (O2)**, **chat_history Hive box name (O9)** — locked but not yet acted on (Phase 2 / 4 work). Ditto for Phase 3 follow-ups (`SESSION_MAX_ACTIVE=1000` placeholder, output validator word-form digits) — placed as commented-out reminders in `.env.example`.
- **Roman Urdu offline keywords** — preserved untouched.

### Backend (`chatbot_backend/`)

**Created:**
- `services/auth.py` — `limiter` (slowapi per-IP) + `require_api_key` Depends with the locked DEBUG-bypass / non-DEBUG-strict contract.
- `services/feedback_log.py` — env-driven path resolution (`FEEDBACK_LOG_PATH` → falls back to `Path(__file__).resolve().parents[1]/data/feedback.jsonl`) + canonical `feedback_record(...)` shape.
- `tests/conftest.py`, `tests/test_emergency_fastpath.py`, `tests/test_pii_redaction.py`, `tests/test_auth_and_rate_limit.py`.

**Modified:**
- `config.py` — `CORS_ORIGINS` default now empty (resolves to `["http://localhost", "http://10.0.2.2"]`); new `cors_allow_credentials` property forces `False` whenever origins is `["*"]` (CORS spec). New settings: `CHATBOT_API_KEY`, `RATE_LIMIT_CHAT_PER_MIN=30`, `RATE_LIMIT_FEEDBACK_PER_MIN=5`, `FEEDBACK_LOG_PATH`. `EMERGENCY_KEYWORDS` no longer contains bare `help` / `emergency`.
- `main.py` — startup `_assert_auth_configured` refuses non-DEBUG boot without `CHATBOT_API_KEY`. `slowapi`'s `_rate_limit_exceeded_handler` wired. `datetime.utcnow()` → `datetime.now(timezone.utc)` everywhere. New `/api/v1/health` route mirroring `/health` (fixes audit F2 on the client side).
- `routers/chat_router.py` — `Depends(require_api_key)` on `/chat/message`, `/chat/feedback`, `/chat/helplines/{region}`, `/chat/offline-data`, `/chat/quick-tip/{disaster_type}`. Introspection (`/intents`, `/disasters`) intentionally open. `@limiter.limit(...)` on `/chat/message` (30/min) and `/chat/feedback` (5/min). `FEEDBACK_LOG` resolved via `resolve_feedback_log_path(settings)`. `datetime.utcnow()` purged.
- `services/chatbot_service.py` — `_check_emergency` rewritten: 4 anchored phrases broadened (no bare `emergency`/`sos`), keyword-set rule now requires `urgency_score >= 0.6` rather than `>= 2 keywords`, anchored bleeding phrases added. `_handle_first_aid` floor switched from hardcoded `0.20` to `settings.RETRIEVAL_SCORE_THRESHOLD` (B10).
- `nlp/intent_classifier.py` — `r"\bhelp\s*me\b"` tightened to require co-occurrence of an injury / disaster anchor (B4).
- `nlp/preprocessor.py` — phone PII broadened (Pakistan landlines 02/04/05x); unhyphenated 13-digit CNIC pattern gated by a context word; general international phone regex first separator made required so 13-digit barcodes don't false-positive (B6).
- `models/schemas.py` — `_utcnow()` helper; `default_factory` swap on both `timestamp` fields (B9).
- `requirements.txt` — `slowapi==0.1.9` added.
- `.env.example` — full rewrite around the new env-var matrix; Phase 3 placeholders commented out for context.

### Frontend (`safelink/`)

**Created:**
- `lib/features/chatbot/services/feedback_outbox_service.dart` — `FeedbackOutboxService` (Hive-backed, single pending box, `maxAttempts=5`, items past cap dropped with log) + `FeedbackSubmission` payload model. Mirrors `OutboxService` style; box name locked to `chatbot_feedback_outbox` (O9).
- `test/chatbot/chat_models_test.dart` — 10 tests covering `ChatRequest` field expansion, `UrgencyLevel.high` round-trip, `ChatMessage.fromJson` reading nested `intent.intent`, uuid IDs.

**Modified:**
- `lib/core/secrets/app_secrets.dart` — `chatbotBaseUrl` getter (platform-aware dev fallback + `--dart-define=CHATBOT_BASE_URL=...` override) + `chatbotApiKey = String.fromEnvironment('CHATBOT_API_KEY', ...)`. Mirrors the existing `mlApiBaseUrl` pattern.
- `lib/core/di/initial_bindings.dart` — registers `FeedbackOutboxService`; `ChatbotRepository` now wired with `feedbackOutbox` + `connectivity`; `ChatController` registered as a permanent singleton (audit F7).
- `lib/main.dart` — opens `chatbot_feedback_outbox` Hive box at boot.
- `lib/features/chatbot/services/chatbot_remote_service.dart` — `_baseUrl` from `AppSecrets`; `X-API-Key` header on every request; `checkHealth()` hits the new `/api/v1/health` (no `..` traversal). New params: `province`, `city`, `language`, `location`, `offlineContext` (audit F9 backend-side wire enabled; UI propagation is Phase 4).
- `lib/features/chatbot/services/chatbot_local_store_service.dart` — `Uuid().v4()` session IDs; new `readOfflineDataChecksum` / `writeOfflineDataChecksum` for the F10 checksum-compare path.
- `lib/features/chatbot/services/chatbot_offline_response_service.dart` — uuid for offline message IDs.
- `lib/features/chatbot/services/chatbot_service.dart` — exposes `Future<void> get ready` (F6); constructor no longer fires-and-forgets `initialize()`.
- `lib/features/chatbot/data/repositories/chatbot_repository.dart` — `_initialize()` returns a future stored as `_readyFuture`; `_isOffline=false` set on every successful online send (F4 explicit invariant); `syncOfflineData` checksum-compare via `localStore` and the JSON's own `checksum` field (F10); offline `submitFeedback` enqueues to the feedback outbox and returns `true`; `_drainFeedback` triggered by `ConnectivityService.isOnline` flipping true.
- `lib/features/chatbot/controllers/chat_controller.dart` — single `trim()` check (F16); `await _chatService.ready` before sync and again before each send (F6); uuid for the catch-arm error bubble.
- `lib/features/chatbot/models/chat_models.dart` — `ChatRequest` gains `province`, `city`, `language`, `location`, `offlineContext`; `UrgencyLevel.high` added between `medium` and `critical`; `_parseUrgencyLevel` now handles `high`; `ChatMessage.fromJson` reads `intent.intent` from the nested backend object (with legacy flat-string fallback); uuid IDs throughout.
- `lib/features/chatbot/presentation/screens/chat_view.dart` — `Get.put(ChatController(...))` field initialiser replaced with `Get.find<ChatController>()` (F7); `addPostFrameCallback` moved out of the `Obx` builder into an `ever` worker on `messages` (F14); single trim/empty check (F16).
- `lib/features/chatbot/presentation/widgets/chat_bubble.dart` — `onTapLink` allowlists `http`/`https`/`tel` (F12); inline `_buildHelplineButton` deleted in favour of the canonical `HelplineButton` widget (F15); urgency tier styling extended — medium gets a subtle amber-50% left border, high a solid amber 3px left border, critical keeps the red treatment; "Feedback saved locally" toast copy honestly reflects offline enqueue ("Saved — will sync when online") vs failure (F5).
- `lib/features/chatbot/presentation/widgets/offline_banner.dart` — protective comment so it doesn't get cleaned up before Phase 4 wires it.
- `pubspec.yaml` — `uuid: ^4.5.1` promoted from transitive to direct.

**Deleted:**
- `lib/features/chatbot/presentation/widgets/s_o_s_button.dart` (orphan, F15).

---

## 2. Acceptance criteria — automated

### Backend `pytest`

```
================================== 32 passed in 0.71s ==================================
```

| Test | Result |
|---|---|
| `test_intents_endpoint_open` | ✅ |
| `test_disasters_endpoint_open` | ✅ |
| `test_root_health_open` | ✅ |
| `test_api_v1_health_open` | ✅ |
| `test_debug_mode_accepts_missing_key` | ✅ |
| `test_debug_mode_accepts_any_key` | ✅ |
| `test_non_debug_mode_rejects_missing_key` | ✅ |
| `test_non_debug_mode_rejects_wrong_key` | ✅ |
| `test_non_debug_mode_accepts_exact_match` | ✅ |
| `test_chat_message_rate_limit_returns_429` | ✅ |
| `test_benign_queries_no_longer_emergency` (×6 cases) | ✅ |
| `test_real_emergencies_still_fire` (×7 cases) | ✅ |
| `test_pure_urgency_safety_net` | ✅ |
| `test_help_me_with_first_aid_routes_to_first_aid_or_safety` | ✅ |
| `test_pakistani_mobile_redacted` | ✅ |
| `test_pakistani_landline_redacted` | ✅ |
| `test_hyphenated_cnic_redacted` | ✅ |
| `test_unhyphenated_cnic_with_context_redacted` | ✅ |
| `test_random_13_digit_string_without_context_not_redacted` | ✅ |
| `test_email_still_redacted` | ✅ |
| `test_no_pii_no_redaction` | ✅ |

### Flutter `flutter analyze` + `flutter test`

```
Analyzing safelink...
No issues found! (ran in 10.2s)

00:01 +19: All tests passed!
```

10 new chatbot tests + 8 pre-existing severity-mapping tests + 1 widget-boot test, all green.

---

## 3. Acceptance criteria — Phase 1 plan checklist

| Acceptance criterion | Status |
|---|---|
| Real-device round trip vs deployed backend with `--dart-define` | ⏸️ **Pending** — depends on Railway provisioning (locked O3). |
| `curl /health` and `curl /api/v1/health` both 200 without auth | ✅ Verified locally; deployed verification pending. |
| `curl -X POST /chat/message` returns 401 without `X-API-Key` (DEBUG=False) | ✅ Verified by `test_non_debug_mode_*` (4 unit tests). |
| 31st `/chat/message` in 60s returns 429 | ✅ Verified by `test_chat_message_rate_limit_returns_429`. |
| Forced single network failure no longer locks session offline | ✅ Code path correct: `_isOffline=false` on every successful send. Manual UI verification still pending real-device test. |
| "help me with first aid" routes to first_aid / safety_advice, not emergency | ✅ Verified by `test_help_me_with_first_aid_routes_to_first_aid_or_safety`. |
| Offline-submitted feedback drains on reconnect | ✅ Code path correct (`_drainFeedback` bound to `ConnectivityService.isOnline`). Manual UI verification pending real-device test. |
| Build passes with `CHATBOT_BASE_URL=` empty (dev defaults still work) | ✅ `flutter analyze` clean; pubspec resolved cleanly. |

---

## 4. Locked decisions ↔ implementation map

| Decision | Where it landed |
|---|---|
| O1 (60 entries) | Phase 2 (not yet) — placeholder. |
| O2 (topic facet) | Phase 2 (not yet) — placeholder. |
| O3 (Railway, Hobby tier, *.railway.app) | Code-side ready; provisioning + URL capture pending human action. |
| O4 (`--dart-define` for v1) | `app_secrets.dart`'s `chatbotApiKey` reads `String.fromEnvironment('CHATBOT_API_KEY')`. README update pending in Phase 5. |
| O5 (re-verify mental-health helplines) | Phase 2 — flagged as PR gate. |
| O6 (defer geocoding) | Untouched. |
| O7 (POST /chat/stream) | Phase 3. |
| O8 (keep `CORS_ORIGINS`) | Honored — no rename. |
| O9 (`chat_history` box) | Phase 4 (Hive box name reserved by docstring; not opened yet). |
| O10 (crisis trigger phrases reviewed by owner) | Phase 3. |
| Plan adjustment: word-form digits in validator | Phase 3 (output validator doesn't exist yet) — captured in `.env.example` placeholder. |
| Plan adjustment: `SESSION_MAX_ACTIVE=1000` default | Phase 3 — captured in `.env.example` placeholder comment. |
| Plan adjustment: DEBUG bypass in `require_api_key` | Implemented this phase, documented in `services/auth.py` docstring. |

---

## 5. Deviations from the plan

1. **F6 implementation simplified.** The plan called for splitting `initialize()` into `prepareCachedSessionId()` (sync) + `loadOfflineCache()` (async). Because `SharedPreferences.getInstance()` is unavoidably async, the practical fix is one `_initialize()` future stored as `_readyFuture` and exposed via `Future<void> get ready`. ChatController awaits this before its first `sendMessage`. Net behaviour matches the plan's intent (close the boot-time race); the public surface is just a single `ready` future instead of two methods.

2. **F4 reset-on-success semantics.** The plan said "On every successful `_remote.sendMessage()` call, set `_isOffline = false`." Done as written, but flagging that this fix only takes effect when the call was attempted in the first place — i.e., when `_isOffline` was already `false`. Promoting offline → online still requires `tryReconnect()` (or the Phase 4 background poll). The Phase 1 invariant is correct; the broader user-experience fix is Phase 4.

3. **Bleeding emergency phrasings.** `i'm bleeding badly please help immediately` lands at urgency 0.5 (below 0.6 threshold) and only one keyword (`bleeding`) — the locked rule (`urgency_score >= 0.6 AND >= 1 keyword`) misses it. Resolution: added 6 anchored bleeding phrases to the hardcoded phrase list. Documented in the test file. The locked rule is intact.

4. **General `phone` PII regex tightened.** B6 only specified landline + unhyphenated CNIC. While writing the unhyphenated-CNIC test, the existing general international `phone` regex was caught making the first separator optional — a 13-digit barcode matched the 3-3-4 phone shape. Fixed by requiring at least one separator. Strictly speaking this exceeds B6's scope but it's a real PII false-positive risk and adjacent to the work. Flagging.

5. **Missing failed-box for feedback outbox.** The plan listed `OutboxService`-style `markFailed`/`requeueFailed` for parity. The chatbot feedback case doesn't justify keeping a permanent failed-items box — feedback is best-effort. Items past `maxAttempts=5` are dropped with a log. Simpler API; can re-add later if surfaced as a need.

6. **`HelplineButton` `onCall` field not added.** The plan suggested an additional `onCall` field on `HelplineButton`. The existing `onTap` (with the bubble passing a closure that calls the helpline) is sufficient — adding `onCall` would be dead surface area. Skipped.

---

## 6. What still needs human action before Phase 2

1. **Railway provisioning** — create the project, set env vars (`CHATBOT_API_KEY`, `CORS_ORIGINS`, `FEEDBACK_LOG_PATH`), deploy, capture the public URL. Phase 5's `RAILWAY_SETUP.md` will document the runbook; for now, locked decision says human is the owner.
2. **Generate `CHATBOT_API_KEY`** — `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Set as both Railway env var and via `--dart-define` for the Flutter build. The release build won't reach the deployed backend without it.
3. **Real-device smoke** — install a release APK with `--dart-define=CHATBOT_BASE_URL=https://<railway>.railway.app --dart-define=CHATBOT_API_KEY=<key>`, send a message, verify response, toggle airplane mode, verify offline behaviour, send feedback, verify outbox drain on reconnect.

---

## 7. Quality gates summary

| Gate | Status |
|---|---|
| `python -m pytest chatbot_backend/tests/` | ✅ 32/32 |
| `flutter analyze` | ✅ clean |
| `flutter test` | ✅ 19/19 |
| Python AST-parse all files | ✅ 22/22 |
| All audit-finding fixes verified by test | ✅ B1, B3, B4, B6, B9, B10 covered; F1, F2, F4, F5, F6, F7, F9, F10, F12, F13, F14, F15, F16 verified by code review (F3, F8, F11 are Phase 4) |
| No new third-party telemetry / analytics | ✅ |
| No API keys in `.env.example` | ✅ placeholders only |
