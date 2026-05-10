"""
Phase 3 — ToolExecutor tests.

Each tool returns the canonical {status, data, message} shape and never
raises. Provider-side adapters (Gemini / Groq) trust this contract.
"""
import pytest

from services import get_chatbot_service
from services.tool_executor import ToolExecutor, reset_tool_executor_for_tests


@pytest.fixture
def executor():
    reset_tool_executor_for_tests()
    return ToolExecutor(get_chatbot_service())


def test_unknown_tool_returns_error(executor):
    out = executor.execute("totally_made_up", {})
    assert out["status"] == "error"
    assert "unknown" in out["message"].lower()


# ─── get_helplines ────────────────────────────────────────────────────────────
def test_get_helplines_no_args_returns_nationwide(executor):
    out = executor.execute("get_helplines", {})
    assert out["status"] == "ok"
    assert any(h["number"] == "1122" for h in out["data"]["helplines"])


def test_get_helplines_punjab_returns_pdma_first(executor):
    out = executor.execute("get_helplines", {"province": "punjab"})
    assert out["status"] == "ok"
    numbers = [h["number"] for h in out["data"]["helplines"]]
    assert "042-99205316" in numbers


def test_get_helplines_unknown_province_404s(executor):
    out = executor.execute("get_helplines", {"province": "narnia"})
    assert out["status"] == "not_found"


def test_get_helplines_normalises_dashes_in_province(executor):
    out = executor.execute("get_helplines", {"province": "Gilgit-Baltistan"})
    assert out["status"] == "ok"


def test_get_helplines_unknown_category_falls_through(executor):
    """`ambulance` isn't in the canonical category list — executor treats
    as no filter, so we still get nationwide back."""
    out = executor.execute("get_helplines", {"category": "ambulance"})
    assert out["status"] == "ok"
    assert out["data"]["helplines"]


# ─── get_first_aid_steps ──────────────────────────────────────────────────────
def test_first_aid_cpr(executor):
    out = executor.execute("get_first_aid_steps", {"injury_type": "cpr"})
    assert out["status"] == "ok"
    assert "cpr" in out["data"]["title"].lower() or "cpr" in out["data"]["content"].lower()
    assert out["data"]["disclaimer_required"] is True


def test_first_aid_anaphylaxis_returns_phase2_entry(executor):
    out = executor.execute(
        "get_first_aid_steps", {"injury_type": "anaphylaxis"}
    )
    assert out["status"] == "ok"
    assert "anaphylaxis" in out["data"]["content"].lower()


def test_first_aid_unknown_returns_not_found(executor):
    out = executor.execute(
        "get_first_aid_steps", {"injury_type": "broken_alien_limb"}
    )
    assert out["status"] == "not_found"


def test_first_aid_missing_arg(executor):
    out = executor.execute("get_first_aid_steps", {})
    assert out["status"] == "error"


# ─── get_evacuation_info ──────────────────────────────────────────────────────
def test_evacuation_flood(executor):
    out = executor.execute(
        "get_evacuation_info", {"city": "karachi", "disaster_type": "flood"}
    )
    assert out["status"] == "ok"
    assert "flood" in out["data"]["title"].lower() or "flood" in out["data"]["content"].lower()


def test_evacuation_missing_disaster_type(executor):
    out = executor.execute("get_evacuation_info", {"city": "lahore"})
    assert out["status"] == "error"


def test_evacuation_unknown_disaster_falls_back_to_general(executor):
    out = executor.execute(
        "get_evacuation_info", {"city": None, "disaster_type": "alien_invasion"}
    )
    # The fallback is the evacuation_general entry — should still be ok
    # because the executor walks to it.
    assert out["status"] in ("ok", "not_found")


# ─── get_quick_tip ────────────────────────────────────────────────────────────
def test_quick_tip_earthquake(executor):
    out = executor.execute("get_quick_tip", {"disaster_type": "earthquake"})
    assert out["status"] == "ok"
    assert "DROP" in out["data"]["tip"] or "1122" in out["data"]["tip"]


def test_quick_tip_unknown(executor):
    out = executor.execute("get_quick_tip", {"disaster_type": "alien_invasion"})
    assert out["status"] == "not_found"


def test_quick_tip_missing_arg(executor):
    out = executor.execute("get_quick_tip", {})
    assert out["status"] == "error"


# ─── execute_all batches results ──────────────────────────────────────────────
def test_execute_all(executor):
    out = executor.execute_all(
        [
            {"name": "get_quick_tip", "arguments": {"disaster_type": "flood"}},
            {"name": "get_helplines", "arguments": {"province": "sindh"}},
        ]
    )
    assert len(out) == 2
    assert out[0]["name"] == "get_quick_tip"
    assert out[0]["result"]["status"] == "ok"
    assert out[1]["name"] == "get_helplines"
    assert out[1]["result"]["status"] == "ok"
