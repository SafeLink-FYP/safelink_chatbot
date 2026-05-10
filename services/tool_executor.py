"""
ToolExecutor — the only path by which the LLM is allowed to obtain
verified data (phone numbers, first-aid steps, evac guidance, quick tips).

Contract (locked):
- Every tool returns ``{"status": "ok"|"not_found"|"error", "data": {...},
  "message": ...}``.
- Tools NEVER raise. Errors are converted to status="error" with a short
  message so the LLM can recover gracefully (e.g., apologise + redirect).
- The LLM is told in the system prompt to paraphrase data fields and never
  to invent beyond them. The output validator strips any phone number not
  in helplines.json regardless.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from models import HelplineInfo

logger = logging.getLogger(__name__)


# Canonical injury_type → KB id-fragment lookup.
_FIRST_AID_INJURY_MAP = {
    "bleeding": "first_aid_bleeding",
    "cpr": "first_aid_cpr",
    "burns": "first_aid_burns",
    "snake_bite": "first_aid_snake_bite",
    "snakebite": "first_aid_snake_bite",
    "snake": "first_aid_snake_bite",
    "electric_shock": "first_aid_electric_shock",
    "electrocution": "first_aid_electric_shock",
    "drowning": "first_aid_drowning",
    "heat_stroke": "first_aid_heat_stroke",
    "heatstroke": "first_aid_heat_stroke",
    "choking": "first_aid_choking",
    "fracture": "first_aid_fracture",
    "broken_bone": "first_aid_fracture",
    # Phase 2 additions
    "hypothermia": "first_aid.during.hypothermia",
    "cold": "first_aid.during.hypothermia",
    "diabetic": "first_aid.during.diabetic_emergency",
    "diabetic_emergency": "first_aid.during.diabetic_emergency",
    "hypoglycaemia": "first_aid.during.diabetic_emergency",
    "hypoglycemia": "first_aid.during.diabetic_emergency",
    "seizure": "first_aid.during.seizure",
    "convulsion": "first_aid.during.seizure",
    "epilepsy": "first_aid.during.seizure",
    "anaphylaxis": "first_aid.during.anaphylaxis",
    "allergic_reaction": "first_aid.during.anaphylaxis",
    "wound_infection": "first_aid.during.wound_infection",
    "wound": "first_aid.during.wound_infection",
}


_VALID_PROVINCES = {
    "punjab", "sindh", "kpk", "balochistan",
    "gilgit_baltistan", "ajk", "islamabad",
}


_HELPLINE_CATEGORIES = {
    "emergency", "medical", "fire", "police", "gas", "disaster",
    "weather", "flood", "women_safety", "child_safety", "mental_health",
    "utility",
}


def _ok(data: Any, message: str = "") -> dict:
    return {"status": "ok", "data": data, "message": message}


def _not_found(message: str) -> dict:
    return {"status": "not_found", "data": {}, "message": message}


def _error(message: str) -> dict:
    return {"status": "error", "data": {}, "message": message}


class ToolExecutor:
    """Glue between LLM tool-call requests and the chatbot's data layer.

    The executor takes references to the same ChatbotService internals that
    the legacy handlers use, so there's a single source of truth for
    helpline lookups and KB retrieval.
    """

    def __init__(self, chatbot_service) -> None:
        # chatbot_service is the running ChatbotService instance. Imports
        # are kept duck-typed to avoid a circular import.
        self.chatbot = chatbot_service

    # ─── Public entry: execute one tool call ─────────────────────────────────
    def execute(self, name: str, arguments: dict | None) -> dict:
        args = arguments or {}
        try:
            if name == "get_helplines":
                return self._get_helplines(
                    province=args.get("province"),
                    category=args.get("category"),
                )
            if name == "get_first_aid_steps":
                return self._get_first_aid_steps(
                    injury_type=args.get("injury_type"),
                )
            if name == "get_evacuation_info":
                return self._get_evacuation_info(
                    city=args.get("city"),
                    disaster_type=args.get("disaster_type"),
                )
            if name == "get_quick_tip":
                return self._get_quick_tip(
                    disaster_type=args.get("disaster_type"),
                )
            return _error(f"unknown tool: {name}")
        except Exception as e:  # never raise back to the LLM loop
            logger.exception("ToolExecutor.execute(%s) failed", name)
            return _error(f"internal error: {e.__class__.__name__}")

    def execute_all(self, calls: list[dict]) -> list[dict]:
        """Execute a batch of {"name": str, "arguments": dict} calls."""
        return [
            {
                "name": call["name"],
                "result": self.execute(call["name"], call.get("arguments")),
            }
            for call in calls
        ]

    # ─── Tools ────────────────────────────────────────────────────────────────
    def _get_helplines(
        self, *, province: Optional[str], category: Optional[str]
    ) -> dict:
        """Wraps ChatbotService._get_helplines with input normalisation."""
        prov = (province or "").strip().lower().replace("-", "_").replace(" ", "_") or None
        cat = (category or "").strip().lower() or None

        if prov and prov not in _VALID_PROVINCES:
            return _not_found(
                f"unknown province `{prov}`; valid: {sorted(_VALID_PROVINCES)}"
            )
        if cat and cat not in _HELPLINE_CATEGORIES:
            # Don't 404 — the LLM might have asked for "ambulance" which
            # maps to medical. Treat as no filter.
            cat = None

        helplines: list[HelplineInfo] = self.chatbot._get_helplines(
            region="pakistan",
            province=prov,
            categories=[cat] if cat else None,
            limit=8,
        )
        if not helplines:
            return _not_found("no helplines matched")

        return _ok(
            {
                "province": prov,
                "category": cat,
                "helplines": [
                    {
                        "name": h.name,
                        "number": h.number,
                        "description": h.description or "",
                        "available_24x7": h.available_24x7,
                    }
                    for h in helplines
                ],
            }
        )

    def _get_first_aid_steps(self, *, injury_type: Optional[str]) -> dict:
        if not injury_type:
            return _error("injury_type is required")
        key = injury_type.strip().lower().replace("-", "_").replace(" ", "_")
        kb_fragment = _FIRST_AID_INJURY_MAP.get(key)
        if not kb_fragment:
            return _not_found(
                f"no first-aid entry for `{injury_type}`. Known: "
                + ", ".join(sorted(set(_FIRST_AID_INJURY_MAP.keys())))
            )
        # Find the entry by id substring match (legacy + v2 ID styles).
        kb = self.chatbot.knowledge_retriever.knowledge_base
        match = next((e for e in kb if kb_fragment in e.get("id", "")), None)
        if not match:
            return _not_found(f"KB entry not found for `{injury_type}`")
        return _ok(
            {
                "injury_type": key,
                "title": match.get("title", ""),
                "content": match.get("content", ""),
                "disclaimer_required": bool(match.get("disclaimer", False)),
                "sources": match.get("sources", []),
            }
        )

    def _get_evacuation_info(
        self, *, city: Optional[str], disaster_type: Optional[str]
    ) -> dict:
        if not disaster_type:
            return _error("disaster_type is required")
        dt = disaster_type.strip().lower()
        kb = self.chatbot.knowledge_retriever
        # Phase-prioritised lookup: during > general > before. The "evacuation"
        # framing is closest to the during-phase content.
        for phase in ("during", "general", "before"):
            results = kb.retrieve(
                f"evacuation {dt} {city or ''}".strip(),
                disaster_type=dt,
                phase=phase,
                top_k=1,
            )
            if results and results[0].score > 0:
                r = results[0]
                return _ok(
                    {
                        "disaster_type": dt,
                        "city": city,
                        "title": r.title,
                        "content": r.content,
                        "phase": phase,
                    }
                )
        # Fall back to the generic evacuation entry.
        for entry in kb.knowledge_base:
            if entry.get("id", "").startswith("evacuation_general"):
                return _ok(
                    {
                        "disaster_type": dt,
                        "city": city,
                        "title": entry.get("title", ""),
                        "content": entry.get("content", ""),
                        "phase": "general",
                    }
                )
        return _not_found(f"no evacuation entry for `{dt}`")

    def _get_quick_tip(self, *, disaster_type: Optional[str]) -> dict:
        if not disaster_type:
            return _error("disaster_type is required")
        dt = disaster_type.strip().lower()
        tips = self.chatbot.templates.get("quick_tips", {}) or {}
        tip = tips.get(dt)
        if not tip:
            return _not_found(
                f"no quick tip for `{dt}`. Available: {sorted(tips.keys())}"
            )
        return _ok({"disaster_type": dt, "tip": tip})


# ─── Singleton ────────────────────────────────────────────────────────────────
_tool_executor: Optional[ToolExecutor] = None


def get_tool_executor(chatbot_service=None) -> ToolExecutor:
    """Lazy singleton. Caller wires the ChatbotService instance the first
    time; subsequent calls return the same executor regardless of arg."""
    global _tool_executor
    if _tool_executor is None:
        if chatbot_service is None:
            from services.chatbot_service import get_chatbot_service

            chatbot_service = get_chatbot_service()
        _tool_executor = ToolExecutor(chatbot_service)
    return _tool_executor


def reset_tool_executor_for_tests() -> None:
    global _tool_executor
    _tool_executor = None
