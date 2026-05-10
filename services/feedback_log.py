"""
Feedback log path resolution + append helper.

Replaces the brittle `os.path.join(__file__, "..", "data", "feedback.jsonl")`
pattern that lived in chat_router.py. In production, point
`settings.FEEDBACK_LOG_PATH` at a mounted volume so feedback survives
redeploys.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def resolve_feedback_log_path(settings) -> Path:
    """
    If FEEDBACK_LOG_PATH is set in env, use it as-is. Otherwise default to
    chatbot_backend/data/feedback.jsonl resolved from this file's location
    (no `cwd`-dependence, works whether uvicorn is run from the repo root
    or from chatbot_backend/).
    """
    configured = (settings.FEEDBACK_LOG_PATH or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "data" / "feedback.jsonl")


def append_feedback(record: Mapping[str, Any], path: Path) -> None:
    """
    Append-only JSONL writer. Failures are logged but do not raise — the
    caller decides whether the API request should fail (today: it doesn't).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to persist feedback to {path}: {e}")


def feedback_record(
    *,
    message_id: str,
    session_id: str | None,
    rating: int | None,
    helpful: bool,
    comment: str | None,
    feedback_text: str | None,
) -> dict[str, Any]:
    """Canonical record shape — keeps writers in lockstep."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
        "session_id": session_id,
        "rating": rating,
        "helpful": helpful,
        "comment": comment,
        "feedback_text": feedback_text,
    }
