"""
Phase 3 — SessionStore tests.

Covers TTL eviction, sliding window, LRU cap. The background sweeper task
isn't started (we'd need an event loop fixture); we exercise sweep_expired()
directly.
"""
import time

import pytest

from services.session_store import SessionStore, _hash_session_id


def _make_store(**overrides) -> SessionStore:
    defaults = dict(max_turns=3, ttl_minutes=1, max_active=5, sweep_interval_seconds=300)
    defaults.update(overrides)
    return SessionStore(**defaults)


def test_append_and_get_basic():
    s = _make_store()
    s.append("sid", "user", "hello")
    s.append("sid", "assistant", "hi there")
    turns = s.get("sid")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].content == "hello"


def test_anonymous_session_id_dropped():
    s = _make_store()
    s.append("", "user", "hello")
    assert s.get("") == []
    assert s.active_session_count() == 0


def test_sliding_window_keeps_last_n_turns():
    s = _make_store(max_turns=2)
    for i in range(5):
        s.append("sid", "user", f"q{i}")
        s.append("sid", "assistant", f"a{i}")
    turns = s.get("sid", max_turns=2)
    # max_turns is in pairs → 2 pairs == 4 messages
    assert len(turns) == 4
    contents = [t.content for t in turns]
    assert "q3" in contents and "q4" in contents
    assert "q0" not in contents


def test_ttl_eviction_via_sweep_expired():
    s = _make_store(ttl_minutes=0)  # 0 minute TTL → immediately expire-eligible
    s.append("sid", "user", "hello")
    # Wait a hair so the cutoff comparison is decisive.
    time.sleep(0.01)
    evicted = s.sweep_expired()
    assert evicted == 1
    assert s.get("sid") == []


def test_lru_eviction_at_cap():
    s = _make_store(max_active=3)
    for sid in ("a", "b", "c"):
        s.append(sid, "user", "hi")
    # At cap. Touch 'a' so it's MRU.
    s.append("a", "user", "again")
    # Add a new session — 'b' should be evicted (least recently used).
    s.append("d", "user", "new")
    assert s.active_session_count() == 3
    assert s.get("b") == []
    assert s.get("a") != []
    assert s.get("d") != []


def test_clear_removes_one_session():
    s = _make_store()
    s.append("a", "user", "hi")
    s.append("b", "user", "hi")
    s.clear("a")
    assert s.get("a") == []
    assert s.get("b") != []


def test_content_truncated_per_turn():
    s = _make_store()
    long = "x" * 2000
    s.append("sid", "user", long)
    turn = s.get("sid")[0]
    # 500-char cap per the implementation
    assert len(turn.content) == 500


def test_session_id_hash_is_deterministic_short():
    h = _hash_session_id("session_abc")
    assert len(h) == 8
    assert h == _hash_session_id("session_abc")
    assert h != _hash_session_id("session_xyz")


def test_get_with_zero_max_turns_still_returns_at_least_one_message():
    s = _make_store(max_turns=3)
    s.append("sid", "user", "hi")
    # Defensive: max_turns=0 shouldn't return [] purely — we cap at 1 message
    # so callers don't get a totally empty history when they asked for some.
    # (Implementation: max(n*2, 1).)
    turns = s.get("sid", max_turns=0)
    assert len(turns) >= 1
