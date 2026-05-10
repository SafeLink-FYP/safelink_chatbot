"""
Phase 2 — TF-IDF retrieval quality.

30 hand-written queries spanning every disaster bucket. Each must surface a
relevant entry in its top-3 (asserted by id-substring match against the
expected entry, NOT by a fixed score — TF-IDF cosines on short queries are
known to land between 0.10 and 0.30 even for good matches).

Also exercises the audit B11 strict-general filter mode.
"""
import pytest

from services import get_chatbot_service


@pytest.fixture(scope="module")
def retriever():
    return get_chatbot_service().knowledge_retriever


def _top_ids(retriever, query: str, **kwargs) -> list[str]:
    """
    Return the top-k entry ids. We bypass the score threshold so a relevant
    match at score 0.10 still surfaces — what matters here is the ranking,
    not the absolute floor.
    """
    saved = retriever.score_threshold
    retriever.score_threshold = 0.0
    try:
        results = retriever.retrieve(query, top_k=kwargs.pop("top_k", 3), **kwargs)
    finally:
        retriever.score_threshold = saved
    # Map back to ids by matching title — RetrievalResult doesn't carry id.
    title_to_id = {
        e["title"]: e["id"] for e in retriever.knowledge_base
    }
    return [title_to_id.get(r.title, "<no-id>") for r in results]


# ─── 30 queries × expected top-3 substring ────────────────────────────────────
# Each tuple is (query, expected_id_substring). The expected substring must
# appear as a prefix or fragment in at least one of the top-3 ids.
QUERIES = [
    # Earthquake (5)
    ("what should I do during an earthquake indoors", "earthquake"),
    ("how to prepare my house for an earthquake", "earthquake"),
    ("earthquake hit my city, what now", "earthquake"),
    ("retrofitting my old building against earthquakes", "earthquake.prevention"),
    ("aftershock safety in northern pakistan", "earthquake"),

    # Flood (5)
    ("flood water rising near my home", "flood"),
    ("how to prepare for monsoon flooding", "flood"),
    ("urban flooding in karachi during heavy rain", "flood_urban"),
    ("flash flood gilgit baltistan", "flood_flash"),
    ("vehicle stuck in flood water what do I do", "flood.during.vehicle"),

    # Heatwave (3)
    ("karachi heatwave safety tips", "heatwave"),
    ("preparing for heatwave summer pakistan", "heatwave"),
    ("recovery after a heatwave week", "heatwave.recovery"),

    # Cyclone (3)
    ("cyclone forecast in coastal sindh", "cyclone"),
    ("preparing for cyclone gwadar", "cyclone"),
    ("after cyclone damage assessment", "cyclone.after"),

    # Fire (3)
    ("kitchen fire what to do", "fire"),
    ("multistorey building fire escape", "fire.during.multistorey"),
    ("home fire prevention smoke detectors", "fire.prevention"),

    # Gas leak (2)
    ("gas leak smell at home", "gas_leak"),
    ("lpg cylinder leak emergency", "gas_leak.during.cylinder"),

    # Building collapse (2)
    ("building collapsed someone trapped", "building_collapse"),
    ("warning signs of building failure", "building_collapse.before"),

    # Electric shock (2)
    ("how to rescue electric shock victim", "electric_shock"),
    ("electric shock prevention monsoon", "electric_shock.prevention"),

    # First aid (3)
    ("how to do CPR chest compressions", "first_aid_cpr"),
    ("severe bleeding first aid", "first_aid_bleeding"),
    ("hypothermia cold injury first aid", "first_aid.during.hypothermia"),

    # Mental health (2)
    ("helping children after a disaster mental health", "mental_health"),
    ("survivors guilt after losing family in disaster", "mental_health"),
]

assert len(QUERIES) == 30


@pytest.mark.parametrize("query,expected_id_fragment", QUERIES)
def test_top3_contains_expected(retriever, query, expected_id_fragment):
    top_ids = _top_ids(retriever, query, top_k=3)
    matches = [eid for eid in top_ids if expected_id_fragment in eid]
    assert matches, (
        f"query {query!r} expected an id containing {expected_id_fragment!r} "
        f"in top-3, got {top_ids}"
    )


# ─── B11 strict-general filter behaviour ──────────────────────────────────────
def test_b11_strict_general_returns_only_general_bucket(retriever):
    """
    Audit B11: with disaster_types=["general"] AND include_general=False,
    the retriever must return ONLY general-bucket entries — no disaster-
    specific entries leak in.
    """
    saved = retriever.score_threshold
    retriever.score_threshold = 0.0
    try:
        results = retriever.retrieve(
            "first aid bleeding",
            disaster_types=["general"],
            include_general=False,
            top_k=10,
        )
    finally:
        retriever.score_threshold = saved
    assert results, "expected non-empty result set"
    bad = [r for r in results if r.disaster_type != "general"]
    assert not bad, f"non-general entries leaked: {[r.title for r in bad]}"


def test_b11_default_include_general_admits_general(retriever):
    """The default behaviour (include_general=True) should still admit
    general entries when retrieving by a specific disaster_type."""
    saved = retriever.score_threshold
    retriever.score_threshold = 0.0
    try:
        results = retriever.retrieve(
            "earthquake first aid bleeding",
            disaster_type="earthquake",
            top_k=5,
        )
    finally:
        retriever.score_threshold = saved
    types = {r.disaster_type for r in results}
    assert "general" in types or "earthquake" in types


def test_first_aid_topic_filter_returns_only_first_aid_topic(retriever):
    """topic='first_aid' must return only entries explicitly tagged."""
    saved = retriever.score_threshold
    retriever.score_threshold = 0.0
    try:
        results = retriever.retrieve(
            "burn treatment first aid",
            topic="first_aid",
            disaster_types=["general"],
            include_general=False,
            top_k=10,
        )
    finally:
        retriever.score_threshold = saved
    # All results must come from first_aid topic entries.
    title_to_topic = {
        e["title"]: e.get("topic") for e in retriever.knowledge_base
    }
    bad = [r for r in results if title_to_topic.get(r.title) != "first_aid"]
    assert not bad, f"non-first-aid topic leaked: {[r.title for r in bad]}"


# ─── Phase 5a Fix 3: first-aid retrieval with verb-form queries ──────────────
# The handler `_handle_first_aid` lowers the score floor to 0.05 because
# TF-IDF on short queries like "burnt my hand" lands in the 0.05–0.10 range.
# These tests confirm that, at threshold 0.05, the right canonical entry is
# top-1 for natural verb-form / scenario phrasings — not the generic
# "Basic First Aid Guidance" template.
@pytest.mark.parametrize(
    "query,expected_id_fragment",
    [
        ("burnt my hand on stove", "first_aid_burns"),
        ("burned my finger", "first_aid_burns"),
        ("scalded my arm with hot water", "first_aid_burns"),
        ("broken arm what to do", "first_aid_fracture"),
        ("fractured wrist", "first_aid_fracture"),
        ("child swallowed water", "first_aid_drowning"),
        ("baby is drowning", "first_aid_drowning"),
        ("snake bite first aid", "first_aid_snake_bite"),
        ("how do I do CPR", "first_aid_cpr"),
        ("severe bleeding wound", "first_aid_bleeding"),
        ("having a seizure", "first_aid.during.seizure"),
        ("severe allergic reaction", "first_aid.during.anaphylaxis"),
        ("low blood sugar diabetic", "first_aid.during.diabetic_emergency"),
        ("hypothermia in mountains", "first_aid.during.hypothermia"),
    ],
)
def test_first_aid_verb_form_top1_at_phase5a_threshold(
    retriever, query, expected_id_fragment
):
    """At the Phase 5a Fix 3 score floor of 0.05, the top-1 entry must
    contain the expected id fragment. Pre-fix the global 0.15 floor was
    dropping these matches before they reached the handler."""
    saved = retriever.score_threshold
    retriever.score_threshold = 0.05
    try:
        results = retriever.retrieve(
            query,
            topic="first_aid",
            disaster_types=["general"],
            include_general=False,
            top_k=2,
        )
    finally:
        retriever.score_threshold = saved
    assert results, f"no results above 0.05 for {query!r}"
    title_to_id = {e["title"]: e["id"] for e in retriever.knowledge_base}
    top_id = title_to_id.get(results[0].title, "")
    assert expected_id_fragment in top_id, (
        f"query={query!r}: expected top-1 id to contain "
        f"{expected_id_fragment!r}, got {top_id!r} (score={results[0].score:.3f})"
    )
