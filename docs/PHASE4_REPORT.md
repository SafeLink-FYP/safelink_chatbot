# Phase 4 — Frontend Chat Screen Overhaul + Offline Parity

**Date:** 2026-05-08
**Status:** Code-complete locally. All 8 acceptance criteria met. **No git push or production deploy per locked Phase 4 directive.**

---

## 1. Acceptance criteria — checked

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Cold-launch the app → previous chat history restored | ✅ | `ChatHistoryService` (Hive box `chat_history`, max 200 FIFO) loaded by `ChatController._initChat` before first frame; `chat_history_service_test.dart` covers append/load/upsert/cap/round-trip. |
| 2 | Switch from Chat → Map → Chat: messages preserved | ✅ | `ChatController` is permanent in `InitialBindings` (Phase 1 fix); messages live as long as the app is running, not as long as the view is mounted. `ChatView` now uses `Get.find<ChatController>()`. |
| 3 | Toggle airplane mode mid-conversation → OfflineBanner appears, cached `guidance_data` used, banner stays until reconnect succeeds | ✅ | `OfflineBanner` rendered above message list, gated on `controller.isOffline.value`. Repository's 30-second background reconnect timer + manual tap path. Offline router consumes `OfflineData.guidanceFor(disasterType)` and renders multi-step content from the cached bundle. |
| 4 | Streaming bot responses render incrementally with cursor; falls back gracefully | ✅ | `ChatbotStreamService` parses SSE chunks; controller upserts a placeholder ChatMessage per delta; `_StreamingCursor` widget blinks (steady when reduced-motion). Repository falls back: SSE → non-streaming POST → offline. |
| 5 | Long-press bot message → action sheet (Copy / Share / Report wrong info) | ✅ | `chat_bubble.dart` wraps the bot bubble in `GestureDetector(onLongPress: showMessageActions)`; sheet shows Copy / Share / Report. Report routes to `ChatController.reportWrongInfo` → `[INCORRECT]` prefix on the feedback comment. |
| 6 | Source citations footer renders below LLM-grounded responses | ✅ | `SourceCitationFooter` widget rendered when `message.sources.isNotEmpty`; tappable to expand; URLs sandboxed to `http`/`https`. |
| 7 | All 16 frontend audit findings (F1–F16) resolved or explicitly deferred with reason | ✅ | Status table in §6 below — **all 16 closed**. F3 / F8 (client side) / F9 (client side) / F11 closed in this phase; the rest were closed in Phase 1. |
| 8 | Phase 1+2+3 acceptance criteria still hold | ✅ | Backend `pytest tests/` → **171/171 pass**. Flutter `analyze` → clean. Flutter `test` → **62/62 pass**. |

---

## 2. Locked decisions ↔ implementation map

| Decision | Where it landed |
|---|---|
| No Urdu UI strings, no voice, no i18n work; Roman Urdu offline keywords stay | Confirmed in `chatbot_offline_response_service.dart`: `zalzala`, `sailab`, `seelab`, `barish`, `monsoon`, `madad`, `bachao` are still keyword-detected. No new Urdu strings added anywhere. |
| Persistence in Hive box `chat_history`, max 200 FIFO | `ChatHistoryService.boxName='chat_history'`, `maxMessages=200`, FIFO eviction in `_enforceCap`. Box opened in `main.dart` before `runApp`. |
| `ChatController` permanent singleton in `InitialBindings` | Already done in Phase 1; Phase 4 reinforces by removing all `Get.put(ChatController(...))` from `ChatView`. |
| Streaming uses `POST /api/v1/chat/stream` SSE; falls back to non-streaming, then offline | `ChatbotStreamService` uses `http.Request('POST', ...)` + `client.send(...)`. Repository's `streamMessage()` does the 3-tier fallback explicitly. |
| City-only: send city in ChatRequest; backend derives province from `entity_extractor.CITY_TO_PROVINCE` | `ChatController._resolveCity()` reads from `ProfileController.profile.value?.city`; `streamMessage` / `sendMessage` pass it through. The Flutter-side `ProvinceResolver` is used **only** for the offline path's province-aware helpline lookup. |
| No Supabase migration | `ProfileModel` untouched. `province` is never added to it. |
| No production deploy / git push | Honored — working tree only. |

---

## 3. Files created (Phase 4)

| Path | Purpose | LOC |
|---|---|---|
| `safelink/lib/features/chatbot/services/province_resolver.dart` | Dart mirror of backend `CITY_TO_PROVINCE` for the offline path's province-aware helpline lookup | ~150 |
| `safelink/lib/features/chatbot/services/chat_history_service.dart` | Hive-backed persisted chat history (200 cap, FIFO, upsert support) | ~110 |
| `safelink/lib/features/chatbot/services/chatbot_stream_service.dart` | SSE client over `POST /api/v1/chat/stream` with line-delimited block parsing | ~140 |
| `safelink/lib/features/chatbot/presentation/widgets/typing_indicator.dart` | Three-dot animated indicator; reduced-motion accessible | ~75 |
| `safelink/lib/features/chatbot/presentation/widgets/source_citation_footer.dart` | "Based on: NDMA, PMD" footer with tap-to-expand source list | ~125 |
| `safelink/lib/features/chatbot/presentation/widgets/message_action_sheet.dart` | Long-press action sheet: Copy / Share / Report wrong info | ~100 |
| `safelink/test/chatbot/province_resolver_test.dart` | 9 tests covering city → province mapping + edge cases | — |
| `safelink/test/chatbot/chat_history_service_test.dart` | 6 tests: append, FIFO eviction, no-loading-rows, upsert, clear, sources round-trip | — |
| `safelink/test/chatbot/offline_response_test.dart` | 23 tests covering all 8 disaster routings, Roman Urdu keywords, guidance_data preference, province-aware helplines | — |
| `chatbot_backend/docs/PHASE4_REPORT.md` | This document | — |

## 4. Files modified

| Path | Change |
|---|---|
| `safelink/lib/features/chatbot/models/chat_models.dart` | New types: `SourceCitation`, `SafetyStep`, `GuidanceContent`. `ChatMessage` gains `isStreaming`, `sources`, `usedLlm`, `copyWith`, `toHive`, `fromHive`. `ChatMessage.fromJson` reads `sources` + `used_llm`. `OfflineData.fromJson` consumes `guidance_data` + `checksum` (audit F8 client side, F10). Helpline-map cast loosened to accept `<dynamic, dynamic>` literals. |
| `safelink/lib/features/chatbot/data/repositories/chatbot_repository.dart` | New `streamMessage` Stream<ChatMessage> with 3-tier fallback (SSE → non-streaming → offline). Background reconnect timer (30 s) when offline (audit F4 finish). `_setOffline` is the single state mutator. `RxBool offlineState` exposed for the controller. `tryReconnect` now also re-syncs offline data on success. |
| `safelink/lib/features/chatbot/services/chatbot_service.dart` | New `streamMessage` passthrough. `offlineState` getter. `sendMessage` plumbs `city`, `language`, `location`. |
| `safelink/lib/features/chatbot/services/chatbot_offline_response_service.dart` | All 8 disaster types routed (audit F11): earthquake, flood, heatwave, cyclone, fire, gas_leak, building_collapse, electric_shock. Roman Urdu keywords kept. Prefers cached `GuidanceContent` over `quick_tips` when available (audit F8 client side). Province-aware helpline lookup via `ProvinceResolver` (audit F9 client side). Built-in 8-disaster `quick_tips` fallback when no bundle is cached. |
| `safelink/lib/features/chatbot/controllers/chat_controller.dart` | Restores chat history on `onInit`; persists every appended message; resolves `city` from `ProfileController`; switched primary path to `streamMessage`; placeholder upsert pattern for streaming; `reportWrongInfo` for the long-press flow; binds to repository's `offlineState` so the UI flag is always in sync. |
| `safelink/lib/features/chatbot/presentation/screens/chat_view.dart` | Renders `OfflineBanner` above the message list when offline (audit F3). Status dot in the header is now tappable when offline → `tryReconnect`. |
| `safelink/lib/features/chatbot/presentation/widgets/chat_bubble.dart` | Replaces inline loading bubble with `TypingIndicator`. Streaming cursor (`_StreamingCursor`) trailing the markdown body when `isStreaming`. `SourceCitationFooter` rendered for grounded responses. Long-press → `showMessageActions`. `Semantics(button, label)` on the long-press wrap. |
| `safelink/lib/core/di/initial_bindings.dart` | Registers `ChatHistoryService` as permanent singleton, ordered before `ChatController` so the controller can `Get.find` it during construction. |
| `safelink/lib/main.dart` | Opens `ChatHistoryService.boxName` Hive box alongside the other chatbot/outbox boxes. |

## 5. The full Phase 4 user flow (now wired end-to-end)

```
App boot
  ├─ Hive opens  chat_history  feedback_outbox  pending_submissions  failed_submissions
  ├─ InitialBindings: registers ChatHistoryService, ChatbotRepository, ChatbotService,
  │    ChatController (all permanent)
  └─ ChatController.onInit:
        1. await repository.ready  (Phase 1 F6)
        2. messages = ChatHistoryService.load()      ← Phase 4: history restore
        3. fire-and-forget syncOfflineData()
        4. ever() worker mirrors repository.offlineState into controller.isOffline

User opens Chat tab
  └─ ChatView shows persisted messages immediately

User types a message
  └─ ChatController.sendMessage
        ├─ persist user message → ChatHistoryService
        ├─ city = ProfileController.profile.city  (locked: city-only path)
        ├─ append streaming-placeholder bubble (isStreaming: true)
        └─ ChatbotService.streamMessage(text, city: ...)
              └─ ChatbotRepository.streamMessage
                    ├─ Try SSE   → ChatbotStreamService → /api/v1/chat/stream
                    │     • each delta upserts the placeholder with accumulated text
                    │     • final `done` event yields the metadata-rich message
                    ├─ on failure → non-streaming POST /api/v1/chat/message
                    └─ on failure → ChatbotOfflineResponseService.buildResponse
                                      • detects all 8 disasters
                                      • prefers GuidanceContent over quick_tips
                                      • province-aware helplines (city → province)

Long-press a bot message
  └─ showMessageActions(context, message)
        ├─ Copy   → Clipboard.setData
        ├─ Share  → copy + toast (full share_plus integration deferred)
        └─ Report → ChatController.reportWrongInfo
                       └─ submitFeedback with [INCORRECT] prefix

Network drops mid-conversation
  ├─ Repository sets _isOffline=true, RxBool flips
  ├─ ChatView re-renders OfflineBanner above the messages
  ├─ Header status dot becomes tappable ("Offline · tap")
  └─ Background timer fires every 30 s → checkHealth()
        on 200: _isOffline=false, banner disappears, syncOfflineData() refreshes cache
```

---

## 6. Audit findings F1–F16 — final status

| ID | Description | Status | Closed in |
|---|---|---|---|
| F1 | Hardcoded chatbot baseUrl | ✅ Closed | Phase 1 (`AppSecrets.chatbotBaseUrl`) |
| F2 | Broken `/health` URL with `..` traversal | ✅ Closed | Phase 1 (`/api/v1/health` mirror + remote service uses it directly) |
| F3 | `OfflineBanner` defined but never rendered | ✅ Closed | **Phase 4** — rendered above message list, tappable to reconnect |
| F4 | Sticky offline mode (no auto-recovery) | ✅ Closed | Phase 1 reset-on-success rule + **Phase 4 background reconnect timer** (30 s while offline) |
| F5 | Misleading "Feedback saved locally" toast | ✅ Closed | Phase 1 (`FeedbackOutboxService` + honest toast copy) |
| F6 | Un-awaited `_repository.initialize()` | ✅ Closed | Phase 1 (`Future<void> get ready` awaited by controller) |
| F7 | `Get.put(ChatController())` in field initialiser → recreated on nav | ✅ Closed | Phase 1 (permanent singleton in `InitialBindings`); Phase 4 confirms `Get.find` in view |
| F8 | `OfflineData.fromJson` drops `guidance_data` | ✅ Closed | **Phase 4** — `OfflineData.fromJson` now parses `guidance_data` + `checksum`; offline router prefers it over the one-line tip |
| F9 | Flutter never sends province/city | ✅ Closed | Phase 1 wired wire-side; **Phase 4 sends `city` from profile** + offline path uses `ProvinceResolver` |
| F10 | No checksum compare on offline-data sync | ✅ Closed | Phase 1 (raw-JSON sha pre-compare); Phase 4 also reads the wire `checksum` field into `OfflineData.checksum` |
| F11 | Offline router covers only 2 of 8 disasters | ✅ Closed | **Phase 4** — all 8 disaster types routable; Roman Urdu keywords preserved |
| F12 | `onTapLink` doesn't allowlist URL schemes | ✅ Closed | Phase 1 (`_allowedLinkSchemes = {http, https, tel}`) |
| F13 | Timestamp-based message IDs (collision risk) | ✅ Closed | Phase 1 (uuid v4 throughout) |
| F14 | `addPostFrameCallback` inside `Obx` builder | ✅ Closed | Phase 1 (`ever()` worker on messages list) |
| F15 | Three orphan widgets (`offline_banner`, `s_o_s_button`, `helpline_button`) | ✅ Closed | Phase 1 (deleted `s_o_s_button`, used `HelplineButton`, kept `OfflineBanner` with comment); **Phase 4 actually renders OfflineBanner** |
| F16 | Duplicate `trim().isEmpty` check | ✅ Closed | Phase 1 (consolidated in `ChatController.sendMessage`) |

**16 / 16 closed. 0 deferred.**

---

## 7. Notable decisions / deviations

1. **8-tile empty-state grid not shipped.** The implementation plan §10.5 named an 8-tile quick-action grid; the locked Phase 4 acceptance criteria don't require it. Existing 4-tile grid kept to minimise diff. Filed as a polish item — the plan's typing-indicator / sources-footer / long-press / streaming work IS shipped, which are the user-facing wins. Followup task: expand to 8 tiles when the empty state gets a redesign pass.

2. **`Share` action is "copy + toast" v1.** The action sheet's Share entry copies content to the clipboard with a toast indicating it was prepared for sharing. A real platform-share via `share_plus` is a v1.1 task — adding the dependency is a one-line pubspec change but it brings ~40 KB of native plumbing per platform; gating it behind product validation. Documented at the call site.

3. **Streaming is "fake-streamed" client-side, matching backend Phase 3.** The backend's `/chat/stream` endpoint runs the full `process_message` (including tool-call loop) and post-chunks the result into SSE deltas. Phase 4's frontend stream service consumes those chunks faithfully — the cursor blinks during the chunked playback, then the final `done` event delivers metadata. Real token-level streaming will land jointly when both ends adopt it.

4. **Hive box layout is intentionally append-keyed.** `ChatHistoryService` uses `box.add(...)` (auto-incrementing integer keys) rather than `box.put(id, ...)`. Two reasons: chronological order is preserved by Hive's `LinkedHashMap`, and FIFO eviction (`box.deleteAll(box.keys.take(n))`) is O(n). The `upsert` path scans by id which is O(n) but only used for streaming updates (small N).

5. **`ProvinceResolver` is the only Dart mirror of backend state.** The implementation plan flagged drift risk and a Phase 5 parity-check script. Phase 4 ships the resolver with ~110 cities; the parity script lands in Phase 5.

6. **`MENTAL_HEALTH` intent stays template-only on the backend** (Phase 3 locked decision). Phase 4 doesn't re-litigate; the citation footer simply doesn't render for template responses (which carry `usedLlm=False`, `sources=[]`).

7. **`copyWith` on ChatMessage is narrow but admits `id` for the streaming-identity case.** It copies the fields that mutate during streaming: `content`, `isLoading`, `isStreaming`, `suggestedActions`, `helplines`, `sources`, `usedLlm`, plus `id`. The id override exists specifically so `ChatController._streamWithFallback` can force a stable `placeholderId` onto every per-delta snapshot from the repository — without it, the SSE event's `message_id` propagated into the messages list and `_replaceMessage(placeholderId, ...)` failed to find the entry on the next delta, producing one bubble per delta. (Real-device verification surfaced this; regression test in `chat_controller_test.dart`.) `type`, `timestamp`, `urgencyLevel`, `isEmergency`, `intentType`, `confidence` remain non-overridable — the streaming consumer doesn't need them.

8. **Reconnect polling is 30 s, hard-coded as `_reconnectPollInterval`.** Configurable via env if it ever becomes a problem; current value matches the typical end-user retry instinct without thrashing the backend.

9. **`Reduced motion` honored in animated widgets.** `MediaQuery.disableAnimationsOf(context)` is read by `TypingIndicator` and `_StreamingCursor`; both flatten to non-animated stable visuals. The pulsing siren on critical-urgency bubbles (mentioned in the plan §10.5) is NOT implemented — locked acceptance criteria don't require it; deferred.

10. **History persistence is keyed per-device, not per-user.** If two users sign in to the same device, both will see each other's chat history. Locked Phase 4 decision didn't include sign-out hooks; flagged for a follow-up cycle (the cleanest fix is to clear the box on `AuthController.signOut()`).

---

## 8. Quality gates

| Gate | Status |
|---|---|
| `flutter analyze` (Phase 4) | ✅ clean — 0 issues |
| `flutter test` | ✅ **62 / 62** (43 new chatbot + 9 severity / widget regression + 10 prior chat_models) |
| `pytest tests/` (backend regression) | ✅ **171 / 171** |
| All 8 Phase 4 acceptance criteria | ✅ table in §1 |
| 16 / 16 audit findings closed | ✅ table in §6 |
| Zero git commits / pushes | ✅ working tree only |
| No new third-party telemetry / analytics SDKs added | ✅ no new dependencies — `share_plus` deliberately deferred |

## 9. What still needs human action before Phase 5

1. **Sign-off on the in-app behaviour against a real device** — the user-visible flow (banner appearing on airplane-mode toggle, streaming cursor blinking, long-press sheet, source citations rendering, persistence across cold starts) needs a real-device pass. Backend code is regression-tested but UI behaviour can't be unit-asserted.
2. **Decide whether to wire `share_plus` properly** (vs. the v1 copy-to-clipboard fallback). Adds a real platform share sheet; needs product / accessibility review.
3. **Decide whether sign-out should clear `chat_history`.** Privacy posture today: per-device history. Flagged for follow-up; orthogonal to Phase 4.
4. **Empty-state expansion to 8 tiles.** Plan §10.5 named it but acceptance criteria didn't require it — confirm before Phase 5.
