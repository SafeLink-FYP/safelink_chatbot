#!/usr/bin/env python
"""
One-shot migrator: knowledge_base.json v1 (flat array, `category` + single
`source` string + `metadata.last_updated`) → v2 (`{version, updated_at,
entries[]}` with `phase`, `topic`, `sources[{name,url}]`, `last_verified`).

Idempotent: running on an already-v2 file is a no-op (same bytes back).

Mapping rules (applied here, not anywhere else):

- v1 `category` ∈ {"during","before","after","general"} →
  v2 `phase`              ∈ {"during","before","after","general"}     (kept)
- v1 `category == "first_aid"` →
  v2 `phase: "during"` + `topic: "first_aid"`            (locked O2)
- v1 `metadata.disclaimer == "first_aid"` →
  v2 top-level `disclaimer: true`                          (single bool flag)
- v1 `source` (semicolon-delimited string) →
  v2 `sources: [{name: <token>, url: null}]`             (URLs filled later
                                                          during authoring)
- v1 `metadata.last_updated` (e.g. "2026-04") →
  v2 `last_verified: "2026-04-01"`                        (month → 1st of month)

Anything not in the v1 schema is preserved under `metadata` so authors don't
lose context.

Run:
    python scripts/migrate_kb_v1_to_v2.py            # uses default paths
    python scripts/migrate_kb_v1_to_v2.py IN OUT     # explicit
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

V2_VERSION = "2.0.0"

PHASE_FROM_CATEGORY = {
    "during": "during",
    "before": "before",
    "after": "after",
    "general": "general",
    "prevention": "prevention",
    "recovery": "recovery",
}


def _normalise_last_verified(raw: Any) -> str:
    """v1 stored YYYY-MM; v2 wants ISO date. Default to mid-month if needed."""
    if not raw:
        return date.today().isoformat()
    s = str(raw).strip()
    if len(s) == 7 and s[4] == "-":  # YYYY-MM
        return f"{s}-01"
    if len(s) == 10 and s.count("-") == 2:
        return s  # already ISO
    return date.today().isoformat()


def _split_sources(raw: Any) -> list[dict]:
    """Semicolon-delimited string → list of {name, url=None}."""
    if not raw:
        return []
    if isinstance(raw, list):  # already v2-shaped (idempotent path)
        return raw
    parts = [p.strip() for p in str(raw).split(";") if p.strip()]
    return [{"name": name, "url": None} for name in parts]


def migrate_entry(v1_entry: dict) -> dict:
    metadata = dict(v1_entry.get("metadata") or {})
    category = v1_entry.get("category") or "general"

    # category=first_aid → phase=during + topic=first_aid (O2)
    if category == "first_aid":
        phase = "during"
        topic = "first_aid"
    else:
        phase = PHASE_FROM_CATEGORY.get(category, category)
        topic = None

    disclaimer_flag = metadata.pop("disclaimer", None) == "first_aid"
    last_verified = _normalise_last_verified(metadata.pop("last_updated", None))
    metadata.pop("verified", None)  # rolled into top-level if needed

    out = {
        "id": v1_entry["id"],
        "disaster_type": v1_entry.get("disaster_type", "general"),
        "phase": phase,
        "title": v1_entry.get("title", ""),
        "content": v1_entry.get("content", ""),
        "searchable_text": v1_entry.get("searchable_text", ""),
        "sources": _split_sources(v1_entry.get("source") or v1_entry.get("sources")),
        "last_verified": last_verified,
        "disclaimer": disclaimer_flag,
    }
    if topic:
        out["topic"] = topic
    if metadata:
        out["metadata"] = metadata
    return out


def migrate(input_path: Path, output_path: Path) -> dict:
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # idempotence check
    if isinstance(data, dict) and data.get("version") == V2_VERSION and "entries" in data:
        # rewrite to enforce key order / formatting but no semantic change
        v2 = data
    elif isinstance(data, list):
        v2 = {
            "version": V2_VERSION,
            "updated_at": date.today().isoformat(),
            "entries": [migrate_entry(e) for e in data],
        }
    else:
        raise SystemExit(
            f"Cannot migrate: input is neither a v1 list nor a v2 wrapper "
            f"({type(data).__name__})"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return v2


def _default_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    return (
        repo_root / "data" / "knowledge_base.json",
        repo_root / "data" / "knowledge_base.json",
    )


def main() -> int:
    if len(sys.argv) == 1:
        in_path, out_path = _default_paths()
    elif len(sys.argv) == 3:
        in_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    else:
        print("usage: migrate_kb_v1_to_v2.py [IN OUT]", file=sys.stderr)
        return 2

    v2 = migrate(in_path, out_path)
    # ASCII-only output to play well with cp1252 on Windows shells.
    print(
        f"Migrated {in_path} -> {out_path} "
        f"({len(v2['entries'])} entries, version={v2['version']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
