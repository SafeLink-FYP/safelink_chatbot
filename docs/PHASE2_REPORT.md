# Phase 2 — KB Migration + Expansion to 60 Entries

**Date:** 2026-05-08
**Status:** Code-complete locally. All acceptance criteria green. **Awaiting human sign-off — no git push, no production deploy per locked Phase 2 directive.**

---

## 1. Acceptance criteria — checked

| Criterion | Status | Evidence |
|---|---|---|
| `python scripts/validate_kb.py` exits 0 | ✅ | `0 error(s), 4 warning(s)` (legacy ID style only) |
| `make test` runs all KB-related tests green | ✅ * | 88/88 backend tests pass; `make` itself isn't installed on Windows but `python -m pytest tests/` runs the same suite |
| `jq '.entries \| length' data/knowledge_base.json` ≈ 60 | ✅ | 62 entries (per-bucket counts win per O1) |
| Every disaster type has at least one entry per its targeted phase set | ✅ | `test_each_disaster_has_during_phase` + `test_per_bucket_counts_meet_locked_targets` |
| 30-query retrieval test all return relevant top-3 | ✅ | `test_retrieval.py` — 30 parametrised cases pass |
| Phase 1 acceptance criteria still hold | ✅ | All Phase 1 backend tests still pass; Flutter `analyze` clean; Flutter test suite 19/19 |

\* `make` is unavailable on this Windows shell. The Makefile targets are correct; they execute via `python -m pytest` and `python scripts/validate_kb.py` directly.

---

## 2. Locked-decision adjustments applied this phase

| Decision | Where it landed |
|---|---|
| O1 — 60 entries, per-bucket counts authoritative | KB now 62 entries; per-bucket targets met exactly. `test_per_bucket_counts_meet_locked_targets` enforces. |
| O2 — `topic` facet in v2 schema | Migration script maps `category=first_aid` → `phase=during + topic=first_aid`. Validator + schema test enforce. New first-aid entries (5) authored with the same shape. |
| B11 in scope | `KnowledgeRetriever._filter_indices` extended with `disaster_types`/`include_general` knobs. `_handle_first_aid` now passes `disaster_types=["general"]` + `include_general=False` so disaster-specific entries don't dilute first-aid retrieval. Phase 3 LLM grounding will use the same filter. |
| O5 — Mental-health helpline re-verification | Live-fetched rozan.org and umang.com.pk on 2026-05-08. Both numbers confirmed (Rozan 0304-111-1741, Umang 0311-7786264). Umang corrected to `available_24x7: true` (previously incorrectly false) and description tightened with the org's own caveat: "NOT for actively suicidal cases — for immediate suicide-risk cases call 115." |
| Source URLs HEAD-checked, warnings only | `validate_kb.py --no-head` (default for `--no-head`) skips probes; `validate_kb.py` (no flag) probes and warns. heart.org and redcross.org both 403 on HEAD (block bot UAs); kept as warnings, not errors. |
| No production deploy / no git push | Honored. All work is local. |

---

## 3. Files created

| Path | Purpose |
|---|---|
| `chatbot_backend/scripts/migrate_kb_v1_to_v2.py` | One-shot migrator. Idempotent. ASCII-safe console output. |
| `chatbot_backend/scripts/validate_kb.py` | Schema + ID + URL HEAD validator. Hard-fails on schema violations; warns on URL errors and last_verified > 6 months old. |
| `chatbot_backend/scripts/seed_kb_v2_phase2.py` | Authoring script — defines 35 new entries inline, applies 2 reclassifications, idempotent on re-run. |
| `chatbot_backend/scripts/update_helplines_phase2.py` | Helplines additive update (verified_at, is_emergency_dispatch, hospital trauma, mental-health corrections). Idempotent. |
| `chatbot_backend/Makefile` | `make validate-kb`, `make test`, `make test-kb`, `make run`, `make migrate-kb`, `make validate-kb-fast`. |
| `chatbot_backend/data/knowledge_base.v1.backup.json` | Pre-migration snapshot for rollback safety. |
| `chatbot_backend/tests/test_kb_schema.py` | 16 v2-schema integrity tests. |
| `chatbot_backend/tests/test_retrieval.py` | 30 parametrised retrieval-quality cases + 3 B11 / topic-filter tests. |
| `chatbot_backend/tests/test_kb_migration.py` | 7 v1→v2 mapping + idempotence tests. |
| `chatbot_backend/docs/PHASE2_REPORT.md` | This document. |

## 4. Files modified

| Path | Change |
|---|---|
| `chatbot_backend/data/knowledge_base.json` | Migrated to v2 (`{version, updated_at, entries[]}`); 27 → 62 entries. |
| `chatbot_backend/data/helplines.json` | Additive: `verified_at`, `is_emergency_dispatch`, 4 hospital trauma centres, mental-health corrections, `last_updated` bumped to 2026-05-08. |
| `chatbot_backend/data/response_templates.json` | Added `disclaimers.first_aid_v2` and `disclaimers.mental_health_v2` (referenced by Phase 3 output validator). |
| `chatbot_backend/nlp/knowledge_retriever.py` | Loads v2 wrapper; tracks `kb_version`; `_filter_indices` extended with `phase`, `topic`, `disaster_types`, `include_general` (B11); search methods plumb the new args; `_result_from_entry` helper unifies v1/v2 entry shape; `get_guidance_by_disaster` reads `phase` then falls back to `category`. |
| `chatbot_backend/services/chatbot_service.py` | `_handle_emergency` uses `phase="during"`; `_handle_first_aid` uses B11 strict-general filter; `_handle_mental_health` queries the new `mental_health` disaster bucket; `_handle_donation` uses `phase="general"`. |

## 5. KB content authored

35 new entries + 2 reclassifications (mental_health_post_disaster_1: dt=general → mental_health, drop topic; cyclone_1: phase=general → during).

| Bucket | Before | After | Δ | Phases covered |
|---|---|---|---|---|
| earthquake | 4 | 8 | +4 | prevention, before×2, during×2, after, recovery, general |
| flood | 5 | 8 | +3 | prevention, before, during×2, after, recovery, general×2 |
| heatwave | 1 | 4 | +3 | prevention, before, during, recovery |
| cyclone | 1 | 4 | +3 | prevention, before, during, after |
| fire | 1 | 4 | +3 | prevention, during×2, after |
| gas_leak | 1 | 4 | +3 | prevention, during×2, after |
| building_collapse | 1 | 4 | +3 | before, during×2, after |
| electric_shock | 0 standalone | 4 | +4 | prevention, during×2, after |
| mental_health | 0 standalone | 5 | +4 | during×5 |
| first_aid topic | 9 | 14 | +5 | (all phase=during, topic=first_aid) |
| general (kit/evac/donation) | 3 | 3 | 0 | unchanged |
| **TOTAL** | **27** | **62** | **+35** | |

Sources used: NDMA Pakistan, PMD, Pakistan Red Crescent (PRCS), AHA, WHO, Geological Survey of Pakistan / USGS, SSGC, SNGPL public safety advisories, Rozan, Umang, Red Cross First Aid. Every entry has at least one source; first-aid + mental-health entries have at least two and a disclaimer flag.

## 6. Helplines updates

- 21 → **25** nationwide helplines (added Indus Karachi, Shifa Islamabad, CMH Lahore, LRH Peshawar — all 24/7 emergency dispatch).
- All 25 entries + 7 PDMAs stamped with `verified_at: "2026-05-08"`.
- New `is_emergency_dispatch` flag — 13 of 25 nationwide helplines flagged true (1122, 115, 15, 16, 1021, 1020, 0311-1112400, AKUH, SKMH, Indus, Shifa, CMH, LRH). PDMAs default to false (coordination, not dispatch). Mental-health, gas (1199), child/women, motorway, bomb-disposal, weather/flood-forecasting all flagged false.
- **Mental-health re-verified live (2026-05-08):**
  - Rozan: 0304-111-1741 (description tightened; not 24/7 per rozan.org).
  - Umang: 0311-7786264 (corrected to 24/7 per umang.com.pk; description now flags it is NOT for actively suicidal cases — those go to 115).

## 7. Deviations / decisions worth flagging

1. **62 entries not 60.** The locked decision said "~60 with per-bucket counts authoritative." Per-bucket targets sum to 62 once the existing 3 general entries (kit / evacuation / donation) are kept. I kept them — they're useful retrieval anchors and removing them would be net-negative. Flagged in `test_total_entries_matches_phase2_target` (range 55–70).

2. **Legacy `*_1` IDs preserved.** The migrator left the v1 ID format intact for the 27 carry-over entries. Renaming would invalidate any external reference / log / future feedback row. Validator warns but doesn't fail — see `test_kb_schema.py` accepts both ID styles. Future cleanup pass can rename if anyone cares.

3. **First-aid disclaimer flag applies to all 14 first-aid entries** (9 carry-over + 5 new). Migrator promoted v1 `metadata.disclaimer = "first_aid"` to top-level `disclaimer: true`; new entries are authored with `disclaimer=True` directly. Phase 3 output validator will read this flag to decide when to append the canonical FIRST_AID_DISCLAIMER.

4. **Mental-health entry `mental_health_post_disaster_1`** was reclassified from `disaster_type=general, topic=first_aid` to `disaster_type=mental_health` (dropped topic). The v1 migration carried over the wrong shape; this is the right home. The 4 new mental-health entries follow the same shape (no topic — mental health is its own bucket).

5. **Existing `cyclone_1` entry's phase changed from `general` to `during`.** Its content is the during-cyclone protocol; the v1 `category=general` was a mis-classification that the migrator carried over. Reclassification was a one-line fix in the seed script.

6. **Hospital trauma-centre numbers are PSTN switchboards from each hospital's public site.** They are the front-door numbers, not the ER direct lines (most Pakistani hospitals don't publish ER direct lines). For a real emergency, 1122/115 still routes faster. Flagged in the description fields.

7. **`heart.org` and `redcross.org` HEAD-check 403** because both block non-browser user agents on HEAD. Their content URLs are reachable in a real browser. Kept as warnings (per locked Phase 2 decision), not errors.

8. **Retrieval threshold tuning unchanged.** The pre-existing 0.15 floor catches most 4–8 word queries but misses very short ones (e.g., `"first aid bleeding"` lands at ~0.13). The 30-query test bypasses the threshold to assert ranking quality, not absolute scores. Tuning the floor is a Phase 3 concern (it interacts with LLM grounding decisions).

9. **`_handle_first_aid` now uses the B11 strict-general filter.** This means earthquake/flood/etc. entries can no longer dilute first-aid retrieval — important for Phase 3 LLM grounding, important for medical accuracy. The change is invisible to the legacy template path because the rule layer dominates anyway.

10. **B11 propagated through all 3 search backends** (semantic, TF-IDF, keyword) plus `_filter_indices`. Backwards compatible — old `disaster_type=` + `category=` calls still work and behave identically.

11. **Searchable_text adjusted for one entry post-test.** `earthquake.prevention.001`'s searchable_text was extended with "retrofitting" + "old building" + "masonry" after the retrieval test surfaced a stemming gap. Documented in the test file's design — TF-IDF doesn't stem, so authored searchable_text must include common phrasings.

## 8. Quality gates

| Gate | Status |
|---|---|
| `python scripts/validate_kb.py --no-head` | ✅ 0 errors, 4 warnings (legacy IDs only) |
| `python scripts/validate_kb.py` (with HEAD checks) | ✅ 0 errors, 6 warnings (legacy IDs + 2 site-blocks-HEAD) |
| `python -m pytest tests/` | ✅ 88/88 (15 Phase 1 + 30 retrieval + 16 schema + 7 migration + 7 PII + 13 auth/limit) |
| `python -c "import json; ..."` smoke-load of v2 KB | ✅ |
| `flutter analyze` | ✅ clean |
| `flutter test` | ✅ 19/19 (Phase 1 frontend untouched) |
| Zero git commits / pushes | ✅ working tree only |

## 9. What still needs human action before Phase 3

1. **Sign off on KB content correctness.** A second pair of eyes on the 35 new entries — especially the 5 new first-aid + 4 new mental-health entries — is the locked Phase 2 hard PR gate. The schema validator can confirm structure, not correctness.
2. **Confirm Umang description language.** The "NOT for actively suicidal cases" warning is taken verbatim from umang.com.pk's own copy. Confirm this is acceptable to surface in chat responses.
3. **Decide whether to rename legacy IDs** (e.g. `earthquake_during_1` → `earthquake.during.indoor.001`). Not blocking; cosmetic. Keep deferred unless someone cares.
4. **Decide whether to commit the v1 backup file** (`data/knowledge_base.v1.backup.json`, 56 KB) to the repo. It's the rollback path. Recommend keeping; small.

## 10. Sign-off checklist (for the human reviewer)

- [ ] Read 5 random entries to confirm content quality.
- [ ] Read all 5 new mental-health entries (highest-stakes content).
- [ ] Read all 5 new first-aid entries (medical liability surface).
- [ ] Confirm no entry invents a phone number not in `helplines.json`.
- [ ] Confirm Rozan 0304-111-1741 and Umang 0311-7786264 are still correct (live-checked 2026-05-08; confirm no further drift).
- [ ] Confirm hospital trauma-centre numbers via each hospital's website if liability matters: Indus 021-111-111-880, Shifa 051-846-4646, CMH Lahore 042-111-130-130, LRH 091-921-1490.
- [ ] Confirm Umang description copy ("NOT for actively suicidal cases — call 115").
- [ ] Run `python scripts/validate_kb.py` locally (warnings expected, no errors).
- [ ] Run `python -m pytest tests/` locally (88 pass).
