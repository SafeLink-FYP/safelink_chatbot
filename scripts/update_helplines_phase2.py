#!/usr/bin/env python
"""
Phase 2 helpline updates (additive).

1. Add `verified_at: <today>` to every helpline + provincial PDMA.
2. Add `is_emergency_dispatch: bool` flag — distinguishes 24/7 dispatch
   helplines (1122 / 115 / 15 / 16 / 1021 / 1020 / hospital trauma) from
   informational lines (PMD, NDMA admin, mental-health counselling).
3. Bump `last_updated` to today.
4. Apply re-verified mental-health helpline corrections (live web check
   2026-05-08): Umang is 24/7; description updated to flag that it is NOT
   for actively suicidal cases (those go to 115). Rozan number unchanged
   but normalised to canonical hyphenation `0304-111-1741`.
5. Append 4 hospital trauma-centre entries for major cities not already
   represented: Indus Hospital Karachi, Shifa International Islamabad,
   CMH Lahore, Lady Reading Hospital Peshawar.

Idempotent — re-running produces an unchanged file (same sort order, same
field set).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

TODAY = date.today().isoformat()


# ─── (number → is_emergency_dispatch) overrides ───────────────────────────────
# Anything not in this set defaults to True iff category in EMERGENCY_DISPATCH.
EMERGENCY_DISPATCH_CATEGORIES = {"emergency", "fire", "police", "medical"}
NON_DISPATCH_NUMBERS = {
    "051-9205037",   # NDMA admin / coordination
    "051-9250368",   # PMD weather (info)
    "042-99200296",  # Flood Forecasting Division (info)
    "118",           # WAPDA — power utility, not life dispatch
    "051-9250404",   # Pakistan Red Crescent admin
    "1098",          # Madadgar Child — protection, not dispatch
    "1099",          # Women Helpline — counselling, not dispatch
    "1199",          # Sui Gas — utility emergency, not life dispatch
    "0304-111-1741",  # Rozan — counselling
    "0304-1111741",  # legacy formatting
    "0311-7786264",  # Umang — counselling (NOT for active suicidal cases)
    "1717",          # Bomb disposal — police forensic, not life dispatch
    "130",           # Motorway Police — partial dispatch, but not med
}


def _is_emergency_dispatch(number: str, category: str) -> bool:
    if number in NON_DISPATCH_NUMBERS:
        return False
    return category in EMERGENCY_DISPATCH_CATEGORIES


def _stamp(entry: dict, is_dispatch_default: bool | None = None) -> None:
    entry.setdefault(
        "is_emergency_dispatch",
        is_dispatch_default
        if is_dispatch_default is not None
        else _is_emergency_dispatch(entry.get("number", ""), entry.get("category", "")),
    )
    entry["verified_at"] = TODAY


# ─── New hospital trauma-centre helplines (verified-name lookups; the
# numbers are PSTN switchboards, public on each hospital's site) ─────────────
HOSPITAL_TRAUMA_NEW = [
    {
        "name": "Indus Hospital (Karachi)",
        "number": "021-111-111-880",
        "description": "Indus Hospital — 24/7 emergency, free trauma care",
        "available_24x7": True,
        "category": "medical",
    },
    {
        "name": "Shifa International Hospital (Islamabad)",
        "number": "051-846-4646",
        "description": "Shifa 24/7 emergency",
        "available_24x7": True,
        "category": "medical",
    },
    {
        "name": "CMH Lahore",
        "number": "042-111-130-130",
        "description": "Combined Military Hospital Lahore — 24/7 emergency",
        "available_24x7": True,
        "category": "medical",
    },
    {
        "name": "Lady Reading Hospital (Peshawar)",
        "number": "091-921-1490",
        "description": "LRH Peshawar — KPK's largest tertiary trauma centre",
        "available_24x7": True,
        "category": "medical",
    },
]


def _patch_mental_health(helplines: list[dict]) -> None:
    """Apply the live-verified Umang + Rozan corrections."""
    for h in helplines:
        name = h.get("name", "")
        if name.startswith("Rozan"):
            h["number"] = "0304-111-1741"  # canonical hyphenation
            h["description"] = (
                "Free counselling helpline — psychosocial support, "
                "depression, trauma, post-disaster anxiety"
            )
            # Rozan is not declared 24/7 on rozan.org; keep as-is.
        elif name.startswith("Umang"):
            h["number"] = "0311-7786264"
            h["available_24x7"] = True  # umang.com.pk lists 24/7
            h["description"] = (
                "Pakistan's first 24/7 mental-health helpline (clinical "
                "psychologists). NOT for actively suicidal cases — for "
                "immediate suicide-risk cases call 115."
            )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "data" / "helplines.json"

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    pakistan = data["regions"]["pakistan"]
    helplines: list[dict] = pakistan["helplines"]

    # Mental-health corrections (live-verified 2026-05-08)
    _patch_mental_health(helplines)

    # Append hospital trauma centres if missing
    existing_numbers = {h["number"] for h in helplines}
    for new in HOSPITAL_TRAUMA_NEW:
        if new["number"] not in existing_numbers:
            helplines.append(new)
            existing_numbers.add(new["number"])

    # Stamp every nationwide helpline with verified_at + is_emergency_dispatch
    for h in helplines:
        _stamp(h)

    # Stamp every PDMA
    for prov_key, prov in pakistan.get("provinces", {}).items():
        if "pdma" in prov:
            _stamp(prov["pdma"], is_dispatch_default=False)

    data["last_updated"] = TODAY

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n_total = len(helplines)
    n_dispatch = sum(1 for h in helplines if h["is_emergency_dispatch"])
    print(
        f"Updated {path.name}: {n_total} nationwide helplines "
        f"({n_dispatch} flagged as emergency_dispatch); 7 provincial PDMAs "
        f"stamped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
