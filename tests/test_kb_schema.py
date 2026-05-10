"""
Phase 2 — v2 KB schema integrity.

Hard checks against `data/knowledge_base.json` (the file the running service
loads). The validate_kb script exercises the same rules; these tests are a
faster regression net for CI / `make test`.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from config import DisasterTypes


KB_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"
)

VALID_PHASES = {"prevention", "before", "during", "after", "recovery", "general"}
VALID_TOPICS = {"first_aid"}
ALLOWED_DT = set(DisasterTypes.all()) | {"mental_health", "electric_shock"}

REQUIRED_FIELDS = (
    "id",
    "disaster_type",
    "phase",
    "title",
    "content",
    "searchable_text",
    "sources",
    "last_verified",
    "disclaimer",
)


@pytest.fixture(scope="module")
def kb():
    with KB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# ─── Top-level shape ──────────────────────────────────────────────────────────
def test_version_is_v2(kb):
    assert kb["version"] == "2.0.0"


def test_has_updated_at(kb):
    assert "updated_at" in kb
    datetime.strptime(kb["updated_at"], "%Y-%m-%d")


def test_entries_is_nonempty_list(kb):
    assert isinstance(kb["entries"], list)
    assert len(kb["entries"]) >= 50


def test_total_entries_matches_phase2_target(kb):
    """Phase 2 target was ~60 with per-bucket counts authoritative (O1)."""
    assert 55 <= len(kb["entries"]) <= 70


# ─── Per-entry validation ─────────────────────────────────────────────────────
def test_every_entry_has_required_fields(kb):
    missing = []
    for e in kb["entries"]:
        for field in REQUIRED_FIELDS:
            if field not in e:
                missing.append((e.get("id", "<no-id>"), field))
    assert not missing, f"missing fields: {missing[:10]}"


def test_phase_values_are_valid(kb):
    bad = [(e["id"], e["phase"]) for e in kb["entries"] if e["phase"] not in VALID_PHASES]
    assert not bad, f"invalid phases: {bad}"


def test_disaster_types_are_valid(kb):
    bad = [
        (e["id"], e["disaster_type"])
        for e in kb["entries"]
        if e["disaster_type"] not in ALLOWED_DT
    ]
    assert not bad, f"invalid disaster_types: {bad}"


def test_topic_values_are_valid_when_present(kb):
    bad = [
        (e["id"], e["topic"])
        for e in kb["entries"]
        if "topic" in e and e["topic"] not in VALID_TOPICS
    ]
    assert not bad, f"invalid topics: {bad}"


def test_ids_are_unique(kb):
    ids = [e["id"] for e in kb["entries"]]
    dups = [i for i in ids if ids.count(i) > 1]
    assert not dups, f"duplicate ids: {dups}"


def test_sources_nonempty_with_name(kb):
    bad = []
    for e in kb["entries"]:
        srcs = e.get("sources")
        if not isinstance(srcs, list) or not srcs:
            bad.append((e["id"], "empty"))
            continue
        for j, s in enumerate(srcs):
            if not isinstance(s, dict) or not s.get("name"):
                bad.append((e["id"], f"sources[{j}] missing name"))
    assert not bad, f"source issues: {bad[:10]}"


def test_last_verified_iso_date(kb):
    bad = []
    for e in kb["entries"]:
        try:
            datetime.strptime(e["last_verified"], "%Y-%m-%d")
        except (ValueError, TypeError, KeyError):
            bad.append(e["id"])
    assert not bad, f"non-ISO last_verified: {bad[:10]}"


def test_disclaimer_is_bool(kb):
    bad = [e["id"] for e in kb["entries"] if not isinstance(e.get("disclaimer"), bool)]
    assert not bad, f"non-bool disclaimer: {bad[:10]}"


# ─── First-aid entries — locked O2 (phase=during + topic=first_aid) ───────────
def test_first_aid_entries_have_phase_during_and_topic_first_aid(kb):
    bad = []
    for e in kb["entries"]:
        if e.get("topic") == "first_aid":
            if e["phase"] != "during":
                bad.append((e["id"], f"phase={e['phase']}"))
    assert not bad, f"first_aid topic with non-during phase: {bad}"


def test_first_aid_entries_carry_disclaimer_flag(kb):
    """Locked: first-aid entries should ship with disclaimer=True so the
    response builder appends the canonical FIRST_AID_DISCLAIMER."""
    bad = [e["id"] for e in kb["entries"] if e.get("topic") == "first_aid" and not e["disclaimer"]]
    assert not bad, f"first_aid entries missing disclaimer flag: {bad}"


# ─── Per-bucket coverage (locked Phase 2 decision) ────────────────────────────
def test_per_bucket_counts_meet_locked_targets(kb):
    """
    Locked Phase 2 targets per bucket (O1, per-bucket counts authoritative):
      earthquake>=8, flood>=8, heatwave>=4, cyclone>=4, fire>=4, gas_leak>=4,
      building_collapse>=4, electric_shock>=4, mental_health>=5,
      first_aid topic>=14.
    """
    from collections import Counter

    by_dt = Counter(e["disaster_type"] for e in kb["entries"])
    topics = Counter(e.get("topic") for e in kb["entries"] if e.get("topic"))

    targets = {
        "earthquake": 8,
        "flood": 8,
        "heatwave": 4,
        "cyclone": 4,
        "fire": 4,
        "gas_leak": 4,
        "building_collapse": 4,
        "electric_shock": 4,
        "mental_health": 5,
    }
    for dt, want in targets.items():
        assert by_dt[dt] >= want, f"{dt}: have {by_dt[dt]}, want >= {want}"
    assert topics["first_aid"] >= 14, f"first_aid topic: have {topics['first_aid']}, want >= 14"


def test_each_disaster_has_during_phase(kb):
    """Every named disaster bucket has at least one `during` entry — the
    panic-window canonical response."""
    needed_dts = ["earthquake", "flood", "heatwave", "cyclone", "fire",
                  "gas_leak", "building_collapse", "electric_shock"]
    have_during = {
        e["disaster_type"]
        for e in kb["entries"]
        if e["phase"] == "during"
    }
    missing = [dt for dt in needed_dts if dt not in have_during]
    assert not missing, f"disasters with no `during` entry: {missing}"
