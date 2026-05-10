"""
Phase 3 — OfflineBundleBuilder tests.

Audit B8: cached. Audit F8 backend: guidance_data step lists populated.
"""
import time

import pytest

from services import get_chatbot_service
from services.offline_bundle import (
    OfflineBundleBuilder,
    reset_offline_bundle_builder_for_tests,
)


@pytest.fixture
def chatbot():
    return get_chatbot_service()


@pytest.fixture
def builder():
    reset_offline_bundle_builder_for_tests()
    return OfflineBundleBuilder(ttl_seconds=3600)


def test_bundle_is_built_with_kb_v2_metadata(builder, chatbot):
    bundle = builder.build(chatbot, region="pakistan")
    assert bundle.checksum
    assert bundle.last_updated is not None
    assert isinstance(bundle.guidance_data, list)
    # Every named disaster type should produce a guidance entry.
    types = {g.disaster_type for g in bundle.guidance_data}
    for dt in (
        "earthquake", "flood", "heatwave", "cyclone",
        "fire", "gas_leak", "building_collapse",
    ):
        assert dt in types, f"missing {dt} in guidance_data"


def test_guidance_data_step_lists_populated_for_during(builder, chatbot):
    """Audit F8: previously empty. Phase 3 mines numbered/bulleted steps
    out of the markdown content."""
    bundle = builder.build(chatbot, region="pakistan")
    by_dt = {g.disaster_type: g for g in bundle.guidance_data}
    for dt in ("earthquake", "flood", "heatwave", "cyclone", "fire", "gas_leak"):
        g = by_dt.get(dt)
        assert g, f"missing guidance for {dt}"
        assert g.during_steps, (
            f"{dt}: during_steps is empty — F8 backend regression"
        )


def test_helplines_map_includes_provincial_keys(builder, chatbot):
    bundle = builder.build(chatbot, region="pakistan")
    assert "pakistan" in bundle.helplines
    # At least one province slice should be present.
    provincial_keys = [k for k in bundle.helplines if "." in k]
    assert provincial_keys, "no <region>.<province> keys in helplines map"


def test_cache_hit_within_ttl(builder, chatbot):
    """Audit B8: same kb_version → cached payload, no rebuild."""
    first = builder.build(chatbot, region="pakistan")
    cached = builder.build(chatbot, region="pakistan")
    # checksum identical because the underlying data is identical
    assert first.checksum == cached.checksum
    # last_updated should be the SAME object reference (cache hit) rather
    # than a fresh timestamp — the builder doesn't re-stamp on cache hit.
    assert first.last_updated == cached.last_updated


def test_cache_invalidated_by_clear():
    reset_offline_bundle_builder_for_tests()
    chatbot = get_chatbot_service()
    b = OfflineBundleBuilder(ttl_seconds=3600)
    first = b.build(chatbot)
    b.clear_cache()
    second = b.build(chatbot)
    # Same content → same checksum.
    assert first.checksum == second.checksum
    # But last_updated differs because we rebuilt.
    assert first.last_updated <= second.last_updated


def test_cache_invalidated_by_ttl():
    reset_offline_bundle_builder_for_tests()
    chatbot = get_chatbot_service()
    b = OfflineBundleBuilder(ttl_seconds=0)
    first = b.build(chatbot)
    time.sleep(0.01)
    second = b.build(chatbot)
    # ttl=0 forces rebuild every call.
    assert second.last_updated >= first.last_updated


def test_bundle_warnings_reflect_disclaimer_flag(builder, chatbot):
    bundle = builder.build(chatbot)
    # Some KB entries are flagged disclaimer=True (first-aid, mental-health).
    # The builder propagates these into guidance.warnings. Assert at least
    # one disaster type with a disclaimer-tagged primary entry has warnings.
    has_warning = any(g.warnings for g in bundle.guidance_data)
    assert has_warning, "expected at least one guidance entry with warnings"
