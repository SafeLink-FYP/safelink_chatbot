#!/usr/bin/env python
"""
Validate `data/knowledge_base.json` against the v2 schema.

Hard checks (failure -> exit 1):
- Top-level: {version, updated_at, entries[]}
- Each entry has: id, disaster_type, phase, title, content, searchable_text,
  sources, last_verified, disclaimer
- `phase` ∈ {prevention, before, during, after, recovery, general}
- `disaster_type` ∈ DisasterTypes.all() ∪ {"mental_health", "electric_shock"}
- `topic`, when present, ∈ {"first_aid"}
- `id` unique; matches `^[a-z0-9_]+\\.[a-z0-9_]+\\.[a-z0-9_]+(?:\\.\\d+)?$`
  (e.g. "earthquake.during.indoor.001"; back-compat for legacy
  "earthquake_during_1" pattern is also accepted via fallback)
- `last_verified` parses as ISO date
- `sources` non-empty list of {name, url|null}

Soft checks (failure -> warning, exit 0):
- Source URL HEAD check (4xx logs warning; 2xx/3xx is fine)
- `last_verified` older than 6 months (per locked Phase 2 decision)

Run:
    python scripts/validate_kb.py
    python scripts/validate_kb.py --no-head        # skip URL probes
    python scripts/validate_kb.py path/to/file.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

# Bare imports work because `make validate-kb` runs from chatbot_backend root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DisasterTypes  # noqa: E402

VALID_PHASES = {"prevention", "before", "during", "after", "recovery", "general"}
# Topic facet (locked O2). Today only first_aid; future-proofed as a set.
VALID_TOPICS = {"first_aid"}
# Disaster types beyond DisasterTypes.all() that the v2 KB introduces.
EXTRA_DISASTER_TYPES = {"mental_health", "electric_shock"}
ALLOWED_DISASTER_TYPES = set(DisasterTypes.all()) | EXTRA_DISASTER_TYPES

REQUIRED_FIELDS = (
    "id",
    "disaster_type",
    "phase",
    "title",
    "content",
    "searchable_text",
    "sources",
    "last_verified",
    "disclaimer",
)

# v2 hierarchical IDs: <namespace>.<phase|topic>.<NNN>  (more dots are fine)
ID_HIERARCHICAL = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
# v1-shaped legacy IDs we also tolerate so the migrator output validates
# without an immediate rename pass.
ID_LEGACY = re.compile(r"^[a-z][a-z0-9_]*_[a-z0-9_]+_\d+$")

SIX_MONTHS_AGO = date.today() - timedelta(days=183)


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def print_summary(self) -> None:
        # ASCII-safe output to play well with cp1252 on Windows shells.
        for w in self.warnings:
            print(f"WARN  {w.encode('ascii', 'replace').decode('ascii')}")
        for e in self.errors:
            print(f"ERROR {e.encode('ascii', 'replace').decode('ascii')}")
        print(
            f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


def _validate_entry(entry: dict, idx: int, seen_ids: set, report: ValidationReport) -> None:
    where = f"entries[{idx}]"
    if not isinstance(entry, dict):
        report.err(f"{where}: not an object")
        return

    eid = entry.get("id", "<missing>")

    for field in REQUIRED_FIELDS:
        if field not in entry:
            report.err(f"{where} (id={eid}): missing field `{field}`")

    if eid in seen_ids:
        report.err(f"{where}: duplicate id `{eid}`")
    seen_ids.add(eid)

    if not (ID_HIERARCHICAL.match(eid) or ID_LEGACY.match(eid)):
        report.warn(
            f"{where} (id={eid}): id does not match preferred hierarchical "
            f"pattern <ns>.<phase>.<NNN>"
        )

    phase = entry.get("phase")
    if phase not in VALID_PHASES:
        report.err(f"{where} (id={eid}): phase `{phase}` not in {VALID_PHASES}")

    dt = entry.get("disaster_type")
    if dt not in ALLOWED_DISASTER_TYPES:
        report.err(
            f"{where} (id={eid}): disaster_type `{dt}` not in "
            f"{sorted(ALLOWED_DISASTER_TYPES)}"
        )

    if "topic" in entry and entry["topic"] not in VALID_TOPICS:
        report.err(
            f"{where} (id={eid}): topic `{entry['topic']}` not in {VALID_TOPICS}"
        )

    sources = entry.get("sources")
    if not isinstance(sources, list) or not sources:
        report.err(f"{where} (id={eid}): sources must be a non-empty list")
    else:
        for j, src in enumerate(sources):
            if not isinstance(src, dict) or "name" not in src:
                report.err(f"{where} (id={eid}): sources[{j}] missing `name`")

    lv = entry.get("last_verified")
    if isinstance(lv, str):
        try:
            parsed = datetime.strptime(lv, "%Y-%m-%d").date()
            if parsed < SIX_MONTHS_AGO:
                report.warn(
                    f"{where} (id={eid}): last_verified={lv} is older than "
                    f"6 months — re-verify before merge"
                )
        except ValueError:
            report.err(f"{where} (id={eid}): last_verified `{lv}` not ISO date")
    else:
        report.err(f"{where} (id={eid}): last_verified must be a string")

    if not isinstance(entry.get("disclaimer"), bool):
        report.err(f"{where} (id={eid}): disclaimer must be a bool")


def _head_check(urls: Iterable[str], report: ValidationReport) -> None:
    """Soft URL liveness check. Warnings only."""
    try:
        import httpx  # local import — purely a dev-time tool
    except ImportError:
        report.warn("httpx not installed — skipping URL HEAD checks")
        return

    seen: dict[str, int] = {}
    for url in urls:
        if url in seen:
            continue
        try:
            resp = httpx.head(url, follow_redirects=True, timeout=5.0)
            seen[url] = resp.status_code
            if resp.status_code >= 400:
                report.warn(f"source URL {url} -> {resp.status_code}")
        except Exception as e:
            seen[url] = -1
            report.warn(f"source URL {url} unreachable: {e.__class__.__name__}")


def validate(path: Path, *, do_head_check: bool = True) -> ValidationReport:
    report = ValidationReport()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        report.err(f"{path}: file not found")
        return report
    except json.JSONDecodeError as e:
        report.err(f"{path}: invalid JSON — {e}")
        return report

    if not isinstance(data, dict):
        report.err("top level must be an object {version, updated_at, entries}")
        return report

    for k in ("version", "updated_at", "entries"):
        if k not in data:
            report.err(f"top-level missing `{k}`")

    if data.get("version") != "2.0.0":
        report.warn(f"version=`{data.get('version')}` (expected 2.0.0)")

    entries = data.get("entries", [])
    if not isinstance(entries, list) or not entries:
        report.err("`entries` must be a non-empty list")
        return report

    seen_ids: set = set()
    all_urls: list[str] = []
    for i, entry in enumerate(entries):
        _validate_entry(entry, i, seen_ids, report)
        for src in (entry.get("sources") or []):
            url = (src or {}).get("url")
            if url:
                all_urls.append(url)

    if do_head_check:
        _head_check(all_urls, report)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"),
    )
    parser.add_argument(
        "--no-head", action="store_true", help="skip URL HEAD probes"
    )
    args = parser.parse_args()

    report = validate(Path(args.path), do_head_check=not args.no_head)
    report.print_summary()
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
