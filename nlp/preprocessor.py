"""
Text Preprocessor for normalising and sanitising user input.

Pakistan-aware spell corrections + PII redaction. No bilingual lexicon —
the chatbot accepts and responds in English; non-English input is detected
in metadata but otherwise passed through.
"""
import re
import unicodedata
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """Handles text normalization, sanitization, and language detection."""

    # ─── Common contractions ──────────────────────────────────────────────────
    CONTRACTIONS = {
        "don't": "do not",
        "doesn't": "does not",
        "didn't": "did not",
        "won't": "will not",
        "wouldn't": "would not",
        "couldn't": "could not",
        "shouldn't": "should not",
        "can't": "cannot",
        "isn't": "is not",
        "aren't": "are not",
        "wasn't": "was not",
        "weren't": "were not",
        "haven't": "have not",
        "hasn't": "has not",
        "hadn't": "had not",
        "i'm": "i am",
        "you're": "you are",
        "he's": "he is",
        "she's": "she is",
        "it's": "it is",
        "we're": "we are",
        "they're": "they are",
        "i've": "i have",
        "you've": "you have",
        "we've": "we have",
        "they've": "they have",
        "i'll": "i will",
        "you'll": "you will",
        "he'll": "he will",
        "she'll": "she will",
        "we'll": "we will",
        "they'll": "they will",
        "i'd": "i would",
        "you'd": "you would",
        "he'd": "he would",
        "she'd": "she would",
        "we'd": "we would",
        "they'd": "they would",
        "what's": "what is",
        "that's": "that is",
        "there's": "there is",
        "here's": "here is",
        "where's": "where is",
        "who's": "who is",
        "how's": "how is",
        "let's": "let us",
    }

    # ─── Spell corrections (English; disaster + Pakistan vocabulary) ──────────
    SPELL_CORRECTIONS = {
        # disasters
        "earthquke": "earthquake",
        "earthquak": "earthquake",
        "eartquake": "earthquake",
        "erthquake": "earthquake",
        "eathquake": "earthquake",
        "flod": "flood",
        "floood": "flood",
        "floodin": "flooding",
        "fier": "fire",
        "firee": "fire",
        "cycloen": "cyclone",
        "cyclon": "cyclone",
        "cyclonic": "cyclone",
        "tsunmi": "tsunami",
        "tsunamie": "tsunami",
        "landslid": "landslide",
        "lanslide": "landslide",
        "pandamic": "pandemic",
        "pandmic": "pandemic",
        "heatwve": "heatwave",
        "heatewave": "heatwave",
        "heat-wave": "heatwave",
        "tornadoe": "tornado",
        "hurricaen": "hurricane",
        "hurican": "hurricane",
        # emergency vocab
        "emergancy": "emergency",
        "emergeny": "emergency",
        "emrgency": "emergency",
        "emergncy": "emergency",
        "helplin": "helpline",
        "helpine": "helpline",
        "sheltr": "shelter",
        "shleter": "shelter",
        "evacuat": "evacuate",
        "evcuate": "evacuate",
        "evacaution": "evacuation",
        "ambulence": "ambulance",
        "ambulnce": "ambulance",
        "rescu": "rescue",
        "rescus": "rescue",
        # first-aid vocab
        "frist": "first",
        "firat": "first",
        "blleding": "bleeding",
        "bleding": "bleeding",
        "frature": "fracture",
        "fractur": "fracture",
        "burnin": "burning",
        "snakebite": "snake bite",
        "electrocution": "electric shock",
        "drownin": "drowning",
        "chokin": "choking",
        # Pakistan-specific phrases the user may write loosely
        "ndma": "NDMA",
        "pdma": "PDMA",
        "kpk": "KPK",
        "ajk": "AJK",
        "gilgit": "Gilgit",
        "balochistan": "Balochistan",
        "baluchistan": "Balochistan",
        "khyber": "KPK",
        "rescue1122": "rescue 1122",
        "edhi": "Edhi",
        "chhipa": "Chhipa",
    }

    # ─── PII patterns ─────────────────────────────────────────────────────────
    # Audit B6 broadened: includes Pakistani landlines (021/042/051/...) and
    # an unhyphenated CNIC variant gated by a context word so we don't redact
    # arbitrary 13-digit runs (timestamps, ID-looking strings).
    PII_PATTERNS = {
        # Hyphenated Pakistan CNIC: 5-7-1 (with or without dashes/spaces)
        "cnic": r"\b\d{5}[-\s]\d{7}[-\s]\d{1}\b",
        # Unhyphenated 13-digit CNIC, requires a nearby context word to
        # avoid false positives on long numeric strings.
        "cnic_unhyphenated": r"\b(?:cnic|nic|id\s*card|id\s*no\.?|identity)\s*[:#-]?\s*(\d{13})\b",
        # Pakistan mobile: +923XXXXXXXXX or 03XXXXXXXXX
        "phone_pk_mobile": r"\b(?:\+?92[-\s]?)?0?3\d{2}[-\s]?\d{7}\b",
        # Pakistan landline: 0XX-NNNNNNN style — Karachi 021, Lahore 042,
        # Islamabad/Pindi 051, Quetta 081, Peshawar 091, etc. Allow 7- or
        # 8-digit subscriber numbers and an optional country prefix.
        "phone_pk_landline": r"\b(?:\+?92[-\s]?)?0[2-9]\d[-\s]?\d{7,8}\b",
        # General phone (international fallback). The first separator is
        # REQUIRED so 13 unbroken digits (CNICs, barcodes, order IDs) don't
        # accidentally match the 3-3-4 phone shape.
        "phone": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]?\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    }

    def __init__(self, anonymize_pii: bool = True):
        self.anonymize_pii = anonymize_pii

    def preprocess(self, text: str) -> Tuple[str, dict]:
        """Main preprocessing pipeline. Returns (processed_text, metadata)."""
        metadata = {
            "original_length": len(text or ""),
            "language": "en",
            "pii_detected": False,
            "was_modified": False,
        }

        if not text or not text.strip():
            return "", metadata

        processed = self._normalize_unicode(text)
        processed = self._normalize_whitespace(processed)
        processed = self._expand_contractions(processed)
        processed = self._fix_spelling(processed)

        processed, pii_found = self._handle_pii(processed)
        metadata["pii_detected"] = pii_found

        metadata["language"] = self._detect_language(processed)
        processed = self._sanitize(processed)

        metadata["was_modified"] = (
            processed.lower().strip() != (text or "").lower().strip()
        )
        metadata["processed_length"] = len(processed)
        return processed.strip(), metadata

    # ─── Steps ────────────────────────────────────────────────────────────────
    def _normalize_unicode(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        return "".join(
            ch for ch in text if unicodedata.category(ch) != "Cc" or ch in "\n\t"
        )

    def _normalize_whitespace(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _expand_contractions(self, text: str) -> str:
        words = text.split()
        out = []
        for word in words:
            lower = word.lower()
            if lower in self.CONTRACTIONS:
                replacement = self.CONTRACTIONS[lower]
                if word and word[0].isupper():
                    replacement = replacement.capitalize()
                out.append(replacement)
            else:
                out.append(word)
        return " ".join(out)

    def _fix_spelling(self, text: str) -> str:
        words = text.split()
        out = []
        for word in words:
            lower = word.lower().strip(".,!?;:")
            if lower in self.SPELL_CORRECTIONS:
                correction = self.SPELL_CORRECTIONS[lower]
                if word and word[0].isupper() and not correction.isupper():
                    correction = correction.capitalize()
                trailing = ""
                for ch in reversed(word):
                    if ch in ".,!?;:":
                        trailing = ch + trailing
                    else:
                        break
                out.append(correction + trailing)
            else:
                out.append(word)
        return " ".join(out)

    def _handle_pii(self, text: str) -> Tuple[str, bool]:
        pii_found = False
        for pii_type, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                pii_found = True
                if self.anonymize_pii:
                    text = re.sub(
                        pattern,
                        f"[REDACTED_{pii_type.upper()}]",
                        text,
                        flags=re.IGNORECASE,
                    )
        return text, pii_found

    def _detect_language(self, text: str) -> str:
        # Char-range heuristic — useful for telemetry only.
        if re.search(r"[ऀ-ॿ]", text):
            return "hi"
        if re.search(r"[؀-ۿ]", text):
            # Arabic / Urdu
            return "ur"
        if re.search(r"[一-鿿]", text):
            return "zh"
        return "en"

    def _sanitize(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"javascript:", "", text, flags=re.IGNORECASE)
        text = re.sub(r"on\w+\s*=", "", text, flags=re.IGNORECASE)
        text = re.sub(r"([!?.]){4,}", r"\1\1\1", text)
        return text

    # ─── Urgency signals ──────────────────────────────────────────────────────
    def extract_urgency_signals(self, text: str) -> dict:
        text_lower = (text or "").lower()
        signals = {
            "has_urgency_words": False,
            "has_distress_words": False,
            "has_time_pressure": False,
            "urgency_score": 0.0,
        }

        urgency_words = [
            "urgent", "emergency", "immediately", "right now", "asap",
            "hurry", "quick", "fast",
        ]
        distress_words = [
            "help", "trapped", "stuck", "dying", "bleeding", "injured",
            "hurt", "pain", "scared", "afraid", "drowning", "unconscious",
            "collapsed",
        ]
        time_words = [
            "right now", "happening now", "currently", "at this moment",
            "ongoing",
        ]

        for w in urgency_words:
            if w in text_lower:
                signals["has_urgency_words"] = True
                signals["urgency_score"] += 0.2
                break
        for w in distress_words:
            if w in text_lower:
                signals["has_distress_words"] = True
                signals["urgency_score"] += 0.3
                break
        for phr in time_words:
            if phr in text_lower:
                signals["has_time_pressure"] = True
                signals["urgency_score"] += 0.2
                break

        signals["urgency_score"] = min(1.0, signals["urgency_score"])
        return signals


# ─── Singleton ────────────────────────────────────────────────────────────────
_preprocessor_instance: Optional[TextPreprocessor] = None


def get_preprocessor(anonymize_pii: bool = True) -> TextPreprocessor:
    global _preprocessor_instance
    if _preprocessor_instance is None:
        _preprocessor_instance = TextPreprocessor(anonymize_pii=anonymize_pii)
    return _preprocessor_instance
