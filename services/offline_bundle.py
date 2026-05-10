"""
OfflineBundleBuilder — Phase 3 fix for ``/api/v1/chat/offline-data``.

Two responsibilities:

1. **Populate `guidance_data`** from the v2 KB. The Phase 1 implementation
   shipped empty step lists (audit F8 partial) — Phase 4 client-side
   consumption depends on real data here.

2. **Cache** the bundle in-process with TTL + checksum invalidation
   (audit B8). Each /offline-data call previously rebuilt the JSON from
   scratch, even though the data is static within a deploy.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from models import GuidanceContent, OfflineDataResponse, SafetyStep

logger = logging.getLogger(__name__)


# Heuristics for splitting the markdown content into "step lists" by phase.
# The KB authors numbered/bulleted lists naturally; we mine those out.
_NUMBERED_STEP_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$", re.MULTILINE)
_BULLET_STEP_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)


def _extract_steps(content: str, *, limit: int = 6) -> list[SafetyStep]:
    """
    Pull the first N actionable steps from the markdown content.
    Numbered steps preferred; bullets are the fallback.
    """
    if not content:
        return []
    matches = _NUMBERED_STEP_RE.findall(content) or _BULLET_STEP_RE.findall(content)
    out: list[SafetyStep] = []
    for i, m in enumerate(matches[:limit], start=1):
        action = re.sub(r"\*\*([^*]+)\*\*", r"\1", m).strip()
        action = action[:240]
        out.append(SafetyStep(step_number=i, action=action, is_critical=(i == 1)))
    return out


def _short_summary(content: str, *, limit: int = 240) -> str:
    """First non-heading paragraph, trimmed."""
    if not content:
        return ""
    for chunk in content.split("\n\n"):
        text = chunk.strip()
        if not text or text.startswith("#"):
            continue
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\s+", " ", text)
        if len(text) > limit:
            text = text[: limit - 3] + "..."
        return text
    return ""


class OfflineBundleBuilder:
    def __init__(self, *, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, OfflineDataResponse]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def build(self, chatbot_service, *, region: str = "pakistan") -> OfflineDataResponse:
        normalized = chatbot_service._normalize_region(region)
        kb_version = getattr(chatbot_service.knowledge_retriever, "kb_version", "unknown")
        cache_key = f"{normalized}|{kb_version}"

        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self.ttl_seconds:
            return cached[1]

        bundle = self._build_uncached(chatbot_service, normalized)
        self._cache[cache_key] = (now, bundle)
        return bundle

    def _build_uncached(
        self, chatbot_service, normalized_region: str
    ) -> OfflineDataResponse:
        kb = chatbot_service.knowledge_retriever.knowledge_base

        # ─── guidance_data: one object per (disaster_type, phase) seed pair ─
        # Group entries by disaster_type, then surface the most useful
        # phases (during > before > after) per disaster.
        guidance_data: list[GuidanceContent] = []

        # Walk every entry once; group by disaster_type to assemble
        # before/during/after step lists per disaster.
        groups: dict[str, dict[str, list[dict]]] = {}
        for entry in kb:
            dt = entry.get("disaster_type", "general")
            phase = entry.get("phase") or entry.get("category") or "general"
            groups.setdefault(dt, {}).setdefault(phase, []).append(entry)

        for dt, by_phase in sorted(groups.items()):
            primary = (
                (by_phase.get("during") or [None])[0]
                or (by_phase.get("before") or [None])[0]
                or (by_phase.get("general") or [None])[0]
            )
            if primary is None:
                continue
            before_list = by_phase.get("before") or []
            during_list = by_phase.get("during") or []
            after_list = by_phase.get("after") or []
            recovery_list = by_phase.get("recovery") or []

            before_steps = _extract_steps(
                "\n\n".join(e.get("content", "") for e in before_list)
            )
            during_steps = _extract_steps(
                "\n\n".join(e.get("content", "") for e in during_list)
            )
            after_steps = _extract_steps(
                "\n\n".join(
                    e.get("content", "") for e in (after_list + recovery_list)
                )
            )

            sources = primary.get("sources") or []
            helpful_links: list[str] = []
            for s in sources:
                if isinstance(s, dict) and s.get("url"):
                    helpful_links.append(s["url"])

            warnings: list[str] = []
            if primary.get("disclaimer"):
                warnings.append(
                    "First-aid guidance — call 115 or 1122 for serious injuries."
                )

            guidance_data.append(
                GuidanceContent(
                    disaster_type=dt,
                    title=primary.get("title", ""),
                    summary=_short_summary(primary.get("content", "")),
                    before_steps=before_steps,
                    during_steps=during_steps,
                    after_steps=after_steps,
                    warnings=warnings,
                    helpful_links=helpful_links[:5],
                )
            )

        # ─── helplines map (region + region.province) ─────────────────────
        helplines_map: dict[str, list] = {}
        helplines_map[normalized_region] = [
            h.model_dump()
            for h in chatbot_service._get_helplines(normalized_region, limit=20)
        ]
        region_data = chatbot_service._region_data(normalized_region)
        provinces = (
            (region_data.get("provinces") or {})
            if isinstance(region_data, dict)
            else {}
        )
        for p_key in provinces.keys():
            helplines_map[f"{normalized_region}.{p_key}"] = [
                h.model_dump()
                for h in chatbot_service._get_helplines(
                    normalized_region, province=p_key, limit=20
                )
            ]

        # ─── quick_tips + emergency_keywords ──────────────────────────────
        quick_tips = chatbot_service.templates.get("quick_tips", {}) or {}
        emergency_keywords = sorted(chatbot_service.emergency_keywords)

        # ─── Stable checksum for client-side cache invalidation ───────────
        digest_src = json.dumps(
            {
                "guidance": [g.model_dump() for g in guidance_data],
                "helplines": helplines_map,
                "quick_tips": quick_tips,
                "emergency_keywords": emergency_keywords,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        checksum = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()

        # Late import to avoid cycle.
        from config import get_settings

        settings = get_settings()
        return OfflineDataResponse(
            version=settings.APP_VERSION,
            last_updated=datetime.now(timezone.utc),
            guidance_data=guidance_data,
            helplines=helplines_map,
            quick_tips=quick_tips,
            emergency_keywords=emergency_keywords,
            checksum=checksum,
        )


# ─── Singleton ────────────────────────────────────────────────────────────────
_builder: Optional[OfflineBundleBuilder] = None


def get_offline_bundle_builder() -> OfflineBundleBuilder:
    global _builder
    if _builder is None:
        from config import get_settings

        settings = get_settings()
        _builder = OfflineBundleBuilder(ttl_seconds=settings.OFFLINE_BUNDLE_TTL_SECONDS)
    return _builder


def reset_offline_bundle_builder_for_tests() -> None:
    global _builder
    _builder = None
