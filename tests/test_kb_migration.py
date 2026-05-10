"""
Phase 2 — migration script idempotence + correctness.

Runs `migrate_kb_v1_to_v2.migrate(...)` against an in-memory v1 fixture and
asserts the v2 output. Also verifies that running the migration on a v2
file is a no-op (idempotence).
"""
import json
from pathlib import Path

import pytest

# Bare imports work because conftest.py prepends chatbot_backend/ to sys.path.
import importlib.util


@pytest.fixture(scope="module")
def migrate_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrate_kb_v1_to_v2.py"
    )
    spec = importlib.util.spec_from_file_location("migrate_kb_v1_to_v2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def v1_fixture(tmp_path):
    """Minimal v1 KB covering the full mapping surface."""
    data = [
        {
            "id": "earthquake_during_x",
            "disaster_type": "earthquake",
            "category": "during",
            "title": "EQ during",
            "content": "Drop, cover, hold.",
            "searchable_text": "earthquake during",
            "source": "NDMA Pakistan; USGS",
            "metadata": {"verified": True, "last_updated": "2026-04"},
        },
        {
            "id": "first_aid_test_1",
            "disaster_type": "general",
            "category": "first_aid",
            "title": "FA test",
            "content": "Apply pressure.",
            "searchable_text": "bleeding pressure",
            "source": "Pakistan Red Crescent",
            "metadata": {"disclaimer": "first_aid", "last_updated": "2026-03"},
        },
        {
            "id": "general_kit_x",
            "disaster_type": "general",
            "category": "before",
            "title": "Kit",
            "content": "Pack a bag.",
            "searchable_text": "kit supplies",
            "source": "NDMA",
            "metadata": {},
        },
    ]
    path = tmp_path / "kb_v1.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v1_to_v2_basic_shape(v1_fixture, tmp_path, migrate_module):
    out = tmp_path / "kb_v2.json"
    migrate_module.migrate(v1_fixture, out)
    v2 = _load(out)

    assert v2["version"] == "2.0.0"
    assert "updated_at" in v2
    assert isinstance(v2["entries"], list)
    assert len(v2["entries"]) == 3


def test_v1_category_during_maps_to_phase_during(v1_fixture, tmp_path, migrate_module):
    out = tmp_path / "kb_v2.json"
    migrate_module.migrate(v1_fixture, out)
    v2 = _load(out)
    eq = next(e for e in v2["entries"] if e["id"] == "earthquake_during_x")
    assert eq["phase"] == "during"
    assert "topic" not in eq  # only first-aid gets topic


def test_v1_category_first_aid_becomes_during_plus_topic(
    v1_fixture, tmp_path, migrate_module
):
    out = tmp_path / "kb_v2.json"
    migrate_module.migrate(v1_fixture, out)
    v2 = _load(out)
    fa = next(e for e in v2["entries"] if e["id"] == "first_aid_test_1")
    assert fa["phase"] == "during"
    assert fa["topic"] == "first_aid"
    # disclaimer flag promoted from metadata to top-level
    assert fa["disclaimer"] is True


def test_v1_source_string_becomes_v2_sources_list(
    v1_fixture, tmp_path, migrate_module
):
    out = tmp_path / "kb_v2.json"
    migrate_module.migrate(v1_fixture, out)
    v2 = _load(out)
    eq = next(e for e in v2["entries"] if e["id"] == "earthquake_during_x")
    names = [s["name"] for s in eq["sources"]]
    assert "NDMA Pakistan" in names
    assert "USGS" in names


def test_v1_last_updated_becomes_iso_last_verified(
    v1_fixture, tmp_path, migrate_module
):
    out = tmp_path / "kb_v2.json"
    migrate_module.migrate(v1_fixture, out)
    v2 = _load(out)
    eq = next(e for e in v2["entries"] if e["id"] == "earthquake_during_x")
    assert eq["last_verified"] == "2026-04-01"


def test_disclaimer_default_false_when_unset(
    v1_fixture, tmp_path, migrate_module
):
    out = tmp_path / "kb_v2.json"
    migrate_module.migrate(v1_fixture, out)
    v2 = _load(out)
    kit = next(e for e in v2["entries"] if e["id"] == "general_kit_x")
    assert kit["disclaimer"] is False


def test_migration_is_idempotent(v1_fixture, tmp_path, migrate_module):
    """Running on v2 output should produce identical bytes."""
    once = tmp_path / "once.json"
    twice = tmp_path / "twice.json"
    migrate_module.migrate(v1_fixture, once)
    migrate_module.migrate(once, twice)
    assert _load(once) == _load(twice)
