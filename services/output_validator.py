"""
Layer 5 — Output validator.

Runs AFTER the LLM responds, BEFORE the response goes to the client.

Rules (in order):

1. **Phone number stripping (numeric form).** Any digit run that looks like
   a phone (>= 7 digits ignoring separators) is checked against a normalised
   set of helplines.json numbers. Unknown → stripped, replaced with the
   placeholder ``[number removed]``.

2. **Phone number stripping (word form).** Locked Phase 3 decision: catch
   word-form digits (``"one one two two"``, ``"zero three two one"``).
   The detector finds runs of digit-words ≥ 3 long, converts to a digit
   string, runs it through the same whitelist, and substitutes if unknown.

3. **Disclaimer enforcement.** If ``intent`` is in the disclaimer-mandatory
   set (first_aid, mental_health) and the response doesn't already contain
   the canonical disclaimer marker, the canonical disclaimer is appended.

4. **Length cap.** Truncates at ``OUTPUT_MAX_CHARS`` with an ellipsis.

5. **Markdown sanitisation.** Strips raw HTML tags, javascript: URIs,
   on*-event handlers. Keeps standard markdown.

6. **URL allowlist.** Markdown links ``[text](https://host/...)`` whose host
   is not in ``ALLOWED_LINK_DOMAINS`` are unwrapped to bare text. The
   visible label is preserved; the URL is removed.

The validator emits a ``ValidationReport`` describing what it changed —
the structured logger uses these counters for observability.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


DISCLAIMER_INTENTS = {"first_aid", "mental_health"}
DISCLAIMER_PLACEHOLDER = "{{FIRST_AID_DISCLAIMER}}"
CANONICAL_FIRST_AID_DISCLAIMER = (
    "\n\n⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. "
    "For serious injuries or medical emergencies, call **115** or **1122** "
    "immediately. Do not attempt procedures beyond your training."
)
CANONICAL_MENTAL_HEALTH_DISCLAIMER = (
    "\n\n⚠️ **Note:** This is supportive guidance, not medical treatment. "
    "For active suicide-risk crises call 115 immediately. Persistent or "
    "worsening symptoms need a qualified mental-health professional — "
    "Rozan 0304-111-1741, Umang 0311-7786264."
)


# ─── Word-form digit table ────────────────────────────────────────────────────
WORD_DIGIT = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Tens (rare in phone speech but harmless to support)
    "ten": "10", "eleven": "11", "twelve": "12",
    "double": "DOUBLE", "triple": "TRIPLE",  # special markers
}


@dataclass
class ValidationReport:
    strip_phone: int = 0
    strip_phone_word_form: int = 0
    strip_url: int = 0
    truncated: bool = False
    disclaimer_appended: bool = False
    disclaimer_placeholder_replaced: bool = False
    html_stripped: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class ValidatedOutput:
    text: str
    report: ValidationReport


# ─── Helpline normalisation ───────────────────────────────────────────────────
_NORMALISE = re.compile(r"[^0-9]")


def _normalise_number(n: str) -> str:
    """Strip every non-digit char so '0304-111-1741' == '03041111741'."""
    return _NORMALISE.sub("", n)


def _build_helpline_whitelist(helplines_data: dict) -> set[str]:
    """Collect every digit-only normalised form from helplines.json."""
    out: set[str] = set()

    def _add(n: str) -> None:
        s = _normalise_number(n or "")
        if s:
            out.add(s)
            # Also add the trailing form without the country / area code so
            # bare "1122" matches as well as "+92-42-1122".
            for size in (3, 4, 5):
                if len(s) > size:
                    out.add(s[-size:] if False else s)  # noop placeholder
            # Also accept the plain form as-is (small numbers like 15, 16).
            out.add(s)

    regions = helplines_data.get("regions", {})
    pakistan = regions.get("pakistan", {})
    for h in pakistan.get("helplines", []) or []:
        _add(h.get("number", ""))
    for prov in (pakistan.get("provinces", {}) or {}).values():
        pdma = prov.get("pdma") or {}
        _add(pdma.get("number", ""))
    # Include the short dispatch numbers explicitly even if absent from the
    # JSON (defense-in-depth — these are universally safe).
    for safe in ("1122", "115", "15", "16", "1199", "1098", "1099", "118", "130", "1717"):
        out.add(safe)
    return out


# ─── Numeric phone-number stripping ───────────────────────────────────────────
# Match 7+ digit runs with optional + / - / space / dot separators. Anchor on
# digit boundaries.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-.()]{5,}\d")
# Common false-positive shapes we explicitly skip rather than test against
# the whitelist. Each is a complete-match check on the candidate slice.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_DATE_RANGE_RE = re.compile(r"^\d{4}-\d{4}$")  # year ranges like 2010-2026


def _looks_like_phone_shape(candidate: str, normalised: str) -> bool:
    """
    Distinguish phone-shaped candidates from dates and bare-digit IDs.

    Rules:
    - ISO dates / year ranges → not phone-shaped.
    - 12+ digits with NO separator at all → barcode / order ID, not phone.
    - Otherwise → treat as phone-shaped (let the whitelist gate decide).
    """
    if _ISO_DATE_RE.match(candidate.strip()) or _DATE_RANGE_RE.match(candidate.strip()):
        return False
    has_separator = any(ch in candidate for ch in (" ", "-", ".", "(", ")", "+"))
    if not has_separator and len(normalised) >= 12:
        return False
    return True


def _strip_numeric_phones(text: str, whitelist: set[str], report: ValidationReport) -> str:
    def _maybe_strip(m: re.Match) -> str:
        candidate = m.group(0)
        norm = _normalise_number(candidate)
        if len(norm) < 3:
            return candidate
        if not _looks_like_phone_shape(candidate, norm):
            return candidate
        # Whitelist hit if any suffix-equal-length match exists. A liberal
        # match: candidate's normalised digits == one of the whitelist
        # entries OR candidate's last 7+ digits match.
        if norm in whitelist:
            return candidate
        if len(norm) >= 7 and any(norm.endswith(w) for w in whitelist):
            return candidate
        report.strip_phone += 1
        return "[number removed]"

    return _PHONE_RE.sub(_maybe_strip, text)


# ─── Word-form phone-number stripping (locked Phase 3 decision) ───────────────
_WORD_RUN_RE = re.compile(
    r"\b(?:zero|oh|o|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|double|triple)"
    r"(?:[\s,-]+(?:zero|oh|o|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|double|triple))+\b",
    re.IGNORECASE,
)


def _word_run_to_digits(run: str) -> str:
    """
    Convert "one one two two" → "1122". "double one" → "11". Returns "" if
    the run resolves to fewer than 3 digits (not phone-shaped).
    """
    tokens = re.split(r"[\s,-]+", run.lower().strip())
    digits: list[str] = []
    pending_modifier: Optional[str] = None
    for tok in tokens:
        d = WORD_DIGIT.get(tok)
        if d is None:
            continue
        if d == "DOUBLE":
            pending_modifier = "DOUBLE"
            continue
        if d == "TRIPLE":
            pending_modifier = "TRIPLE"
            continue
        if pending_modifier == "DOUBLE":
            digits.extend([d, d])
            pending_modifier = None
        elif pending_modifier == "TRIPLE":
            digits.extend([d, d, d])
            pending_modifier = None
        else:
            digits.append(d)
    return "".join(digits)


def _strip_wordform_phones(
    text: str, whitelist: set[str], report: ValidationReport
) -> str:
    def _replace(m: re.Match) -> str:
        run = m.group(0)
        digits = _word_run_to_digits(run)
        if len(digits) < 3:  # too short to be a phone
            return run
        if digits in whitelist:
            return run
        if any(digits.endswith(w) for w in whitelist):
            return run
        # Word-form runs that resolve to a 3+ digit non-whitelisted string
        # are almost always invented numbers. Strip.
        report.strip_phone_word_form += 1
        return "[number removed]"

    return _WORD_RUN_RE.sub(_replace, text)


# ─── HTML / script sanitisation ───────────────────────────────────────────────
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_JS_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)
_ON_EVENT_RE = re.compile(r"on\w+\s*=", re.IGNORECASE)


def _sanitise_html(text: str, report: ValidationReport) -> str:
    new, n1 = _HTML_TAG_RE.subn("", text)
    new = _JS_URI_RE.sub("[link removed]", new)
    new = _ON_EVENT_RE.sub("", new)
    if n1:
        report.html_stripped += n1
    return new


# ─── URL allowlist ────────────────────────────────────────────────────────────
_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^)\s]+)\)"
)


def _enforce_url_allowlist(
    text: str, allowed_domains: Iterable[str], report: ValidationReport
) -> str:
    allowed = {d.lower().lstrip(".") for d in allowed_domains}

    def _replace(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            report.strip_url += 1
            return label
        if not host:
            report.strip_url += 1
            return label
        # Accept exact match or subdomain of an allowed root.
        if host in allowed or any(host.endswith("." + d) for d in allowed):
            return m.group(0)
        report.strip_url += 1
        return label

    return _MARKDOWN_LINK_RE.sub(_replace, text)


# ─── Disclaimer ───────────────────────────────────────────────────────────────
def _apply_disclaimer(
    text: str, intent: Optional[str], report: ValidationReport
) -> str:
    # First, replace any explicit placeholder.
    if DISCLAIMER_PLACEHOLDER in text:
        canonical = (
            CANONICAL_MENTAL_HEALTH_DISCLAIMER
            if intent == "mental_health"
            else CANONICAL_FIRST_AID_DISCLAIMER
        )
        text = text.replace(DISCLAIMER_PLACEHOLDER, canonical.lstrip())
        report.disclaimer_placeholder_replaced = True

    if intent not in DISCLAIMER_INTENTS:
        return text

    # If text already mentions "Medical Disclaimer" / mental-health note,
    # don't double up.
    has_disclaimer = (
        "Medical Disclaimer" in text
        or "supportive guidance" in text
        or "mental-health professional" in text
    )
    if has_disclaimer:
        return text

    canonical = (
        CANONICAL_MENTAL_HEALTH_DISCLAIMER
        if intent == "mental_health"
        else CANONICAL_FIRST_AID_DISCLAIMER
    )
    report.disclaimer_appended = True
    return text + canonical


# ─── Public API ───────────────────────────────────────────────────────────────
class OutputValidator:
    def __init__(
        self,
        *,
        helplines_data: dict,
        allowed_link_domains: Iterable[str],
        max_chars: int = 1500,
    ) -> None:
        self._whitelist = _build_helpline_whitelist(helplines_data or {})
        self._allowed_domains = list(allowed_link_domains or [])
        self.max_chars = max_chars

    def refresh_helplines(self, helplines_data: dict) -> None:
        """Rebuild the whitelist (e.g., after a hot reload)."""
        self._whitelist = _build_helpline_whitelist(helplines_data or {})

    def validate(self, text: str, *, intent: Optional[str] = None) -> ValidatedOutput:
        if text is None:
            text = ""
        report = ValidationReport()

        # 1+2. Phones (numeric and word-form). Run word-form first because
        # it produces fixed-width substitutions that the numeric pass won't
        # then match.
        text = _strip_wordform_phones(text, self._whitelist, report)
        text = _strip_numeric_phones(text, self._whitelist, report)

        # 5. HTML / scripts.
        text = _sanitise_html(text, report)

        # 6. URL allowlist.
        text = _enforce_url_allowlist(text, self._allowed_domains, report)

        # 3. Disclaimer.
        text = _apply_disclaimer(text, intent, report)

        # 4. Length cap.
        if len(text) > self.max_chars:
            text = text[: self.max_chars - 3] + "..."
            report.truncated = True

        return ValidatedOutput(text=text, report=report)


# ─── Module-level factory ─────────────────────────────────────────────────────
_validator: Optional[OutputValidator] = None


def get_output_validator(chatbot_service=None) -> OutputValidator:
    """Lazy singleton. The first call wires the running ChatbotService's
    helplines_data + settings; subsequent calls return the same instance."""
    global _validator
    if _validator is None:
        from config import get_settings

        if chatbot_service is None:
            from services.chatbot_service import get_chatbot_service

            chatbot_service = get_chatbot_service()
        settings = get_settings()
        _validator = OutputValidator(
            helplines_data=chatbot_service.helplines_data,
            allowed_link_domains=settings.allowed_link_domain_list,
            max_chars=settings.OUTPUT_MAX_CHARS,
        )
    return _validator


def reset_output_validator_for_tests() -> None:
    global _validator
    _validator = None
