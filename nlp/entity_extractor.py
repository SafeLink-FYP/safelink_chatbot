"""
Entity Extractor — Pakistan-aware regex + (optional) spaCy NER.

Extracts location, phone, time, quantity, injury, severity, address, and
disaster-specific details. Adds province detection (city → province mapping).
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    entity_type: str
    value: str
    normalized_value: str
    confidence: float
    start: int
    end: int
    source: str = "regex"


class EntityExtractor:
    """Extracts entities relevant to disaster relief in Pakistan."""

    # ─── Pakistan locations ───────────────────────────────────────────────────
    LOCATION_PATTERNS = [
        # Provinces / regions / territories
        r"\b(punjab|sindh|balochistan|baluchistan|khyber\s+pakhtunkhwa|kpk|gilgit[\s-]?baltistan|gb|azad\s+(jammu\s+and\s+)?kashmir|ajk|islamabad\s+capital\s+territory|ict|fata)\b",
        # Major cities (de-duped, lowercased)
        r"\b(karachi|lahore|faisalabad|rawalpindi|multan|hyderabad|gujranwala|peshawar|quetta|islamabad|bahawalpur|sargodha|sialkot|sukkur|larkana|sheikhupura|jhang|rahim\s+yar\s+khan|mardan|gujrat|kasur|mingora|dera\s+ghazi\s+khan|sahiwal|nawabshah|okara|mirpur|chiniot|kamoke|sadiqabad|burewala|jacobabad|muzaffargarh|muridke|jhelum|shikarpur|hafizabad|kohat|khanewal|dadu|gojra|mandi\s+bahauddin|abbottabad|tando\s+allahyar|daska|pakpattan|bahawalnagar|tando\s+adam|khairpur|chishtian|attock|vehari|dera\s+ismail\s+khan|chakwal|swabi|swat|chitral|bannu|nowshera|mansehra|turbat|khuzdar|zhob|gwadar|hub|lasbela|gilgit|skardu|hunza|chilas|muzaffarabad|kotli|rawalakot|bhimber|bagh|haripur|charsadda|battagram|dir|shangla|buner|tank|ghizer|astore|shigar|kharmang|ghanche|diamer|chaman|loralai|dera\s+bugti|noshki|mastung|qila\s+saifullah)\b",
        # Generic location prepositions
        r"\b(near|in|at|around)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
        r"\bmy\s+(area|locality|neighborhood|neighbourhood|city|town|village|district|tehsil|province|mohalla|gali|nullah|colony|sector)\b",
    ]

    # ─── Pakistani phone patterns ─────────────────────────────────────────────
    PHONE_PATTERNS = [
        r"\b(?:\+?92[-\s]?)?0?3\d{2}[-\s]?\d{7}\b",
        r"\b(?:\+?92[-\s]?)?0?[1-9][0-9]{1,2}[-\s]?\d{7,8}\b",
        r"\b1[0-9]{2,3}\b",
        r"\b15\b|\b16\b",
    ]

    TIME_PATTERNS = [
        r"\b(\d{1,2})\s*(hours?|hrs?|minutes?|mins?|days?|weeks?)\s*(ago|back|before)?\b",
        r"\b(yesterday|today|tonight|this\s+morning|this\s+evening|last\s+night|tomorrow)\b",
        r"\b(since|for)\s+(\d+)\s*(hours?|days?|minutes?)\b",
        r"\b(just\s+now|right\s+now|currently|at\s+the\s+moment|ongoing)\b",
    ]

    QUANTITY_PATTERNS = [
        r"\b(\d+)\s*(people|persons|individuals|victims|casualties|injured|dead|missing|trapped)\b",
        r"\b(many|several|few|some|hundreds?|thousands?)\s*(people|persons|victims)?\b",
        r"\b(family|families|children|kids|elderly|women|men|infants?)\b",
    ]

    INJURY_PATTERNS = [
        r"\b(injured|hurt|wounded|bleeding|unconscious|trapped|stuck|burned|broken|fractured)\b",
        r"\b(heart\s+attack|stroke|seizure|difficulty\s+breathing|chest\s+pain|severe\s+pain)\b",
        r"\b(minor|serious|severe|critical|life-threatening)\s*(injury|injuries|condition)?\b",
    ]

    SEVERITY_PATTERNS = [
        r"\b(minor|small|slight|little)\b",
        r"\b(moderate|medium|significant)\b",
        r"\b(major|severe|serious|large|big|massive|huge|devastating)\b",
        r"\b(catastrophic|extreme|unprecedented|worst)\b",
    ]

    ADDRESS_PATTERNS = [
        r"\b(\d+)\s*,?\s*([A-Za-z\s]+)\s*,?\s*(street|st|road|rd|avenue|ave|lane|ln|block|sector|phase)\b",
        r"\b(sector|block|phase|plot)\s*[-]?\s*(\d+[a-z]?)\b",
        r"\bpin\s*(?:code)?\s*[-:]?\s*(\d{4,6})\b",
    ]

    DISASTER_ENTITY_PATTERNS = {
        "earthquake": [
            r"\b(\d+(?:\.\d+)?)\s*(?:magnitude|richter|on\s+the\s+richter\s+scale)\b",
            r"\b(aftershock|tremor|seismic)\b",
        ],
        "flood": [
            r"\b(\d+)\s*(feet|ft|meters?|m|inches?|in)\s*(of)?\s*water\b",
            r"\bwater\s*level\s*(\d+)\b",
            r"\b(rising|receding|stagnant)\s*water\b",
        ],
        "heatwave": [
            r"\b(\d+)\s*(?:degrees?|°c|°f)\b",
        ],
        "fire": [
            r"\b(kitchen|electrical|cylinder|forest|building|car)\s+fire\b",
            r"\b(smoke|flames|burning|combustion)\b",
        ],
        "gas_leak": [
            r"\b(gas\s+smell|rotten\s+egg\s+smell|hissing\s+sound)\b",
        ],
    }

    # ─── Pakistan city → province mapping ─────────────────────────────────────
    CITY_TO_PROVINCE = {
        # Punjab
        "lahore": "punjab", "faisalabad": "punjab", "rawalpindi": "punjab",
        "multan": "punjab", "gujranwala": "punjab", "sialkot": "punjab",
        "bahawalpur": "punjab", "sargodha": "punjab", "sheikhupura": "punjab",
        "rahim yar khan": "punjab", "jhang": "punjab", "kasur": "punjab",
        "okara": "punjab", "sahiwal": "punjab", "wah cantt": "punjab",
        "dera ghazi khan": "punjab", "gujrat": "punjab", "chakwal": "punjab",
        "attock": "punjab", "jhelum": "punjab", "mandi bahauddin": "punjab",
        "mianwali": "punjab", "khanewal": "punjab", "muzaffargarh": "punjab",
        "vehari": "punjab", "pakpattan": "punjab", "bahawalnagar": "punjab",
        "muridke": "punjab", "kamoke": "punjab", "chiniot": "punjab",
        "burewala": "punjab", "sadiqabad": "punjab", "hafizabad": "punjab",
        "daska": "punjab", "chishtian": "punjab", "gojra": "punjab",
        # Sindh
        "karachi": "sindh", "hyderabad": "sindh", "sukkur": "sindh",
        "larkana": "sindh", "mirpur khas": "sindh", "nawabshah": "sindh",
        "shaheed benazirabad": "sindh", "khairpur": "sindh", "jacobabad": "sindh",
        "shikarpur": "sindh", "dadu": "sindh", "thatta": "sindh",
        "badin": "sindh", "tando allahyar": "sindh", "tando adam": "sindh",
        "umerkot": "sindh", "ghotki": "sindh",
        # KPK
        "peshawar": "kpk", "mardan": "kpk", "abbottabad": "kpk",
        "swabi": "kpk", "kohat": "kpk", "mansehra": "kpk", "swat": "kpk",
        "mingora": "kpk", "chitral": "kpk", "bannu": "kpk",
        "nowshera": "kpk", "dera ismail khan": "kpk", "haripur": "kpk",
        "charsadda": "kpk", "battagram": "kpk", "dir": "kpk",
        "shangla": "kpk", "buner": "kpk", "tank": "kpk",
        # Balochistan
        "quetta": "balochistan", "gwadar": "balochistan",
        "turbat": "balochistan", "khuzdar": "balochistan",
        "hub": "balochistan", "chaman": "balochistan", "zhob": "balochistan",
        "dera bugti": "balochistan", "loralai": "balochistan",
        "lasbela": "balochistan", "mastung": "balochistan",
        "qila saifullah": "balochistan", "noshki": "balochistan",
        # GB
        "gilgit": "gilgit_baltistan", "skardu": "gilgit_baltistan",
        "hunza": "gilgit_baltistan", "chilas": "gilgit_baltistan",
        "ghizer": "gilgit_baltistan", "astore": "gilgit_baltistan",
        "shigar": "gilgit_baltistan", "kharmang": "gilgit_baltistan",
        "ghanche": "gilgit_baltistan", "diamer": "gilgit_baltistan",
        # AJK
        "muzaffarabad": "ajk", "mirpur": "ajk", "kotli": "ajk",
        "rawalakot": "ajk", "bhimber": "ajk", "bagh": "ajk",
        "neelum": "ajk", "haveli": "ajk", "sudhanoti": "ajk",
        # ICT
        "islamabad": "islamabad",
    }

    PROVINCE_PATTERNS = {
        "punjab": r"\bpunjab\b",
        "sindh": r"\bsindh\b",
        "kpk": r"\b(kpk|khyber\s+pakhtunkhwa|khyber-?pakhtunkhwa)\b",
        "balochistan": r"\b(balochistan|baluchistan)\b",
        "gilgit_baltistan": r"\b(gilgit[\s-]?baltistan|gb)\b",
        "ajk": r"\b(ajk|azad\s+(jammu\s+(and|&)\s+)?kashmir)\b",
        "islamabad": r"\b(islamabad|ict|capital\s+territory)\b",
    }

    def __init__(self, use_spacy: bool = False):
        self.use_spacy = use_spacy
        self.nlp = None
        if use_spacy:
            self._load_spacy()

    def _load_spacy(self):
        try:
            import spacy

            self.nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model loaded successfully")
        except ImportError:
            logger.warning("spaCy not installed, using regex-only extraction")
            self.use_spacy = False
        except OSError:
            logger.warning("spaCy model not found, using regex-only extraction")
            self.use_spacy = False

    # ─── Public extract ───────────────────────────────────────────────────────
    def extract(
        self, text: str, disaster_context: Optional[str] = None
    ) -> List[ExtractedEntity]:
        entities: List[ExtractedEntity] = []
        entities.extend(self._extract_locations(text))
        entities.extend(self._extract_phone_numbers(text))
        entities.extend(self._extract_time_references(text))
        entities.extend(self._extract_quantities(text))
        entities.extend(self._extract_injuries(text))
        entities.extend(self._extract_severity(text))
        entities.extend(self._extract_addresses(text))

        if disaster_context and disaster_context in self.DISASTER_ENTITY_PATTERNS:
            entities.extend(self._extract_disaster_specific(text, disaster_context))

        if self.use_spacy and self.nlp:
            entities.extend(self._extract_with_spacy(text))

        return self._deduplicate_entities(entities)

    def _extract_with_pattern(
        self,
        text: str,
        patterns: List[str],
        entity_type: str,
        confidence: float = 0.8,
    ) -> List[ExtractedEntity]:
        entities = []
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                value = m.group(0)
                entities.append(
                    ExtractedEntity(
                        entity_type=entity_type,
                        value=value,
                        normalized_value=value.lower().strip(),
                        confidence=confidence,
                        start=m.start(),
                        end=m.end(),
                        source="regex",
                    )
                )
        return entities

    def _extract_locations(self, text: str) -> List[ExtractedEntity]:
        return self._extract_with_pattern(text, self.LOCATION_PATTERNS, "location", 0.85)

    def _extract_phone_numbers(self, text: str) -> List[ExtractedEntity]:
        entities = []
        for pat in self.PHONE_PATTERNS:
            for m in re.finditer(pat, text):
                value = m.group(0)
                normalized = re.sub(r"[-\s\(\)]", "", value)
                entities.append(
                    ExtractedEntity(
                        entity_type="phone",
                        value=value,
                        normalized_value=normalized,
                        confidence=0.9,
                        start=m.start(),
                        end=m.end(),
                        source="regex",
                    )
                )
        return entities

    def _extract_time_references(self, text: str) -> List[ExtractedEntity]:
        return self._extract_with_pattern(text, self.TIME_PATTERNS, "time", 0.8)

    def _extract_quantities(self, text: str) -> List[ExtractedEntity]:
        return self._extract_with_pattern(text, self.QUANTITY_PATTERNS, "quantity", 0.75)

    def _extract_injuries(self, text: str) -> List[ExtractedEntity]:
        return self._extract_with_pattern(text, self.INJURY_PATTERNS, "injury", 0.85)

    def _extract_severity(self, text: str) -> List[ExtractedEntity]:
        entities = []
        text_lower = text.lower()
        severity_map = {
            "low": self.SEVERITY_PATTERNS[0],
            "medium": self.SEVERITY_PATTERNS[1],
            "high": self.SEVERITY_PATTERNS[2],
            "critical": self.SEVERITY_PATTERNS[3],
        }
        for level, pat in severity_map.items():
            for m in re.finditer(pat, text_lower, re.IGNORECASE):
                entities.append(
                    ExtractedEntity(
                        entity_type="severity",
                        value=m.group(0),
                        normalized_value=level,
                        confidence=0.8,
                        start=m.start(),
                        end=m.end(),
                        source="regex",
                    )
                )
        return entities

    def _extract_addresses(self, text: str) -> List[ExtractedEntity]:
        return self._extract_with_pattern(text, self.ADDRESS_PATTERNS, "address", 0.7)

    def _extract_disaster_specific(
        self, text: str, disaster_type: str
    ) -> List[ExtractedEntity]:
        return self._extract_with_pattern(
            text, self.DISASTER_ENTITY_PATTERNS.get(disaster_type, []),
            f"{disaster_type}_detail", 0.8,
        )

    def _extract_with_spacy(self, text: str) -> List[ExtractedEntity]:
        entities: List[ExtractedEntity] = []
        if not self.nlp:
            return entities
        try:
            doc = self.nlp(text)
            label_map = {
                "GPE": "location", "LOC": "location", "FAC": "location",
                "PERSON": "person", "ORG": "organization",
                "DATE": "time", "TIME": "time",
                "CARDINAL": "quantity", "QUANTITY": "quantity",
            }
            for ent in doc.ents:
                t = label_map.get(ent.label_, "other")
                if t != "other":
                    entities.append(
                        ExtractedEntity(
                            entity_type=t,
                            value=ent.text,
                            normalized_value=ent.text.lower(),
                            confidence=0.75,
                            start=ent.start_char,
                            end=ent.end_char,
                            source="spacy",
                        )
                    )
        except Exception as e:
            logger.error(f"spaCy extraction failed: {e}")
        return entities

    def _deduplicate_entities(
        self, entities: List[ExtractedEntity]
    ) -> List[ExtractedEntity]:
        seen = {}
        for e in entities:
            key = (e.entity_type, e.normalized_value)
            if key not in seen or e.confidence > seen[key].confidence:
                seen[key] = e
        return list(seen.values())

    # ─── Region / province helpers ────────────────────────────────────────────
    def extract_region(self, text: str, default: str = "pakistan") -> str:
        """Extract country-level region (used to pick helplines.json bucket)."""
        text_lower = (text or "").lower()
        country_patterns = {
            "pakistan": r"\b(pakistan|pakistani|pk)\b",
        }
        for country, pat in country_patterns.items():
            if re.search(pat, text_lower):
                return country
        return default

    def extract_province(
        self, text: str, city_hint: Optional[str] = None
    ) -> Optional[str]:
        """Detect Pakistani province via direct mention or city → province map."""
        text_lower = (text or "").lower()

        # 1. Direct province mention
        for province, pat in self.PROVINCE_PATTERNS.items():
            if re.search(pat, text_lower, re.IGNORECASE):
                return province

        # 2. City → province (from text)
        for city, province in self.CITY_TO_PROVINCE.items():
            # word boundary safe match
            if re.search(rf"\b{re.escape(city)}\b", text_lower):
                return province

        # 3. City hint from request
        if city_hint:
            return self.CITY_TO_PROVINCE.get(city_hint.lower())

        return None

    def detect_disaster_type(self, text: str) -> Optional[str]:
        """Public alias used by the service layer."""
        text_lower = (text or "").lower()
        from nlp.intent_classifier import IntentClassifier

        for disaster_type, pat in IntentClassifier.DISASTER_PATTERNS.items():
            if re.search(pat, text_lower, re.IGNORECASE):
                return disaster_type
        return None

    # Backwards-compat
    def _detect_disaster_type(self, text: str) -> Optional[str]:
        return self.detect_disaster_type(text)


# ─── Singleton ────────────────────────────────────────────────────────────────
_extractor_instance: Optional[EntityExtractor] = None


def get_entity_extractor(use_spacy: bool = False) -> EntityExtractor:
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = EntityExtractor(use_spacy=use_spacy)
    return _extractor_instance
