"""
In-memory ephemeral conversation history.

Phase 3 v1: a simple per-process dict + LRU + TTL sweep. Sessions are NOT
persisted across restarts (this is the deliberate v1 trade-off — a hard
session reset on redeploy is preferable to risking PII durability).

Storage shape::

    session_id -> deque[ChatTurn]   (sliding window, capped at SESSION_MAX_TURNS*2)

Eviction policy:

- TTL: a session is dropped after SESSION_TTL_MINUTES of inactivity. The
  background sweeper runs every SESSION_SWEEP_INTERVAL_SECONDS.
- LRU: when the active session count would exceed SESSION_MAX_ACTIVE, the
  least-recently-used session is dropped.

Logging discipline:

- We log session_id_hash (sha256[:8]) — never the raw session_id, never the
  message content. Length-only metrics for content (audit B5).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class _SessionState:
    turns: deque[ChatTurn]
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _hash_session_id(session_id: str) -> str:
    """Short stable hash for logging — never reverse-engineer back to id."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]


class SessionStore:
    """Per-process conversation memory.

    Thread-safety: `append` / `get` / `clear` are NOT goroutine-safe under
    asyncio.gather concurrent traffic. FastAPI default is single-threaded
    per request; under uvicorn workers each worker has its own store and
    sessions don't span workers. Acceptable for v1.
    """

    def __init__(
        self,
        *,
        max_turns: int,
        ttl_minutes: int,
        max_active: int,
        sweep_interval_seconds: int = 300,
    ) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_minutes * 60
        self.max_active = max_active
        self.sweep_interval = sweep_interval_seconds
        # OrderedDict gives us O(1) move-to-end for LRU semantics.
        self._sessions: OrderedDict[str, _SessionState] = OrderedDict()
        # Buffer holds twice the visible window so we don't lose context
        # mid-rollover during a long turn.
        self._buffer_capacity = max(max_turns * 4, 12)
        self._sweeper_task: Optional[asyncio.Task] = None

    # ─── Public API ───────────────────────────────────────────────────────────
    def append(self, session_id: str, role: str, content: str) -> None:
        if not session_id:
            return  # anonymous request — no memory
        # Cap content per turn so a runaway prompt can't blow memory.
        truncated = content[:500] if isinstance(content, str) else ""
        state = self._sessions.get(session_id)
        if state is None:
            state = _SessionState(
                turns=deque(maxlen=self._buffer_capacity),
            )
            self._sessions[session_id] = state
        else:
            self._sessions.move_to_end(session_id)
        state.turns.append(ChatTurn(role=role, content=truncated))
        state.last_seen = datetime.now(timezone.utc)
        self._enforce_lru_cap()

    def get(self, session_id: str, max_turns: Optional[int] = None) -> list[ChatTurn]:
        if not session_id:
            return []
        state = self._sessions.get(session_id)
        if state is None:
            return []
        self._sessions.move_to_end(session_id)
        n = max_turns if max_turns is not None else self.max_turns
        # max_turns is in conversational pairs — each pair is user + assistant.
        msgs = max(n * 2, 1)
        return list(state.turns)[-msgs:]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def active_session_count(self) -> int:
        return len(self._sessions)

    # ─── Maintenance ──────────────────────────────────────────────────────────
    def _enforce_lru_cap(self) -> None:
        while len(self._sessions) > self.max_active:
            evicted_id, _ = self._sessions.popitem(last=False)
            logger.info(
                "SessionStore: LRU eviction sid_hash=%s active=%d",
                _hash_session_id(evicted_id),
                len(self._sessions),
            )

    def sweep_expired(self) -> int:
        """One-shot sweep. Returns the number of sessions evicted."""
        cutoff = datetime.now(timezone.utc).timestamp() - self.ttl_seconds
        evicted = 0
        # Materialise to a list so we can mutate during iteration.
        for sid, state in list(self._sessions.items()):
            if state.last_seen.timestamp() < cutoff:
                self._sessions.pop(sid, None)
                evicted += 1
        if evicted:
            logger.info(
                "SessionStore: TTL sweep evicted=%d active=%d",
                evicted,
                len(self._sessions),
            )
        return evicted

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.sweep_interval)
                self.sweep_expired()
        except asyncio.CancelledError:
            return

    def start_sweeper(self) -> None:
        """Kick off the periodic TTL sweep. Idempotent."""
        if self._sweeper_task is None or self._sweeper_task.done():
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # No running loop yet (e.g., test environment) — caller can
                # start the sweep manually via sweep_expired().
                return
            self._sweeper_task = loop.create_task(self._sweep_loop())

    async def stop_sweeper(self) -> None:
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass


# ─── Module-level singleton ───────────────────────────────────────────────────
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        # Late import to avoid a config import cycle at module load time.
        from config import get_settings

        settings = get_settings()
        _session_store = SessionStore(
            max_turns=settings.SESSION_MAX_TURNS,
            ttl_minutes=settings.SESSION_TTL_MINUTES,
            max_active=settings.SESSION_MAX_ACTIVE,
            sweep_interval_seconds=settings.SESSION_SWEEP_INTERVAL_SECONDS,
        )
    return _session_store


def reset_session_store_for_tests() -> None:
    """Test-only: drop the singleton so a fresh instance is built next call."""
    global _session_store
    _session_store = None
