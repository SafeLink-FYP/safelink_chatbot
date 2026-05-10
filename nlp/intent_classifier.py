"""
Intent Classification — hybrid rules + ML (Logistic Regression).

Designed for Pakistan-context disaster relief queries. Persists the trained
classifier to disk via joblib so cold starts on Railway are fast (no retrain).
"""
import os
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple
import logging

import numpy as np
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from config import IntentTypes, get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class IntentPrediction:
    intent: str
    confidence: float
    sub_intent: Optional[str] = None
    method: str = "hybrid"  # rule | ml | hybrid | empty


class IntentClassifier:
    """Hybrid rule + Logistic Regression classifier."""

    # ─── Phase 5a Fix 1: short-query disaster shortcut keywords ──────────────
    # Maps every accepted disaster keyword (English + Roman Urdu, single- and
    # multi-word) to the canonical disaster_type. When a 1-3 token message
    # contains exactly one of these, we route directly to safety_advice with
    # the matching sub_intent at confidence 0.85, bypassing the ML layer.
    #
    # On-device verification (Phase 4) showed that bare nouns like "flood",
    # "fire", "zalzala" were landing in `fallback` because the ML classifier
    # was returning `fallback` with high enough confidence to skip the
    # disaster-nudge path. This shortcut resolves that without retraining.
    _SHORT_QUERY_KEYWORDS_SINGLE = {
        # English
        "flood": "flood",
        "floods": "flood",
        "flooding": "flood",
        "flooded": "flood",
        "earthquake": "earthquake",
        "earthquakes": "earthquake",
        "quake": "earthquake",
        "tremor": "earthquake",
        "tremors": "earthquake",
        "shaking": "earthquake",
        "fire": "fire",
        "burning": "fire",
        "heatwave": "heatwave",
        "cyclone": "cyclone",
        "hurricane": "cyclone",
        "typhoon": "cyclone",
        # Roman Urdu — locked Phase 4 decision keeps these in routing surface.
        "sailab": "flood",
        "seelab": "flood",
        "zalzala": "earthquake",
        "bhonchaal": "earthquake",
        "aag": "fire",
    }
    # Multi-word keywords matched as a contiguous substring of the lowercased
    # message (still subject to the ≤3 token guard).
    _SHORT_QUERY_KEYWORDS_PHRASES = {
        "gas leak": "gas_leak",
        "sui gas": "gas_leak",
        "building collapse": "building_collapse",
        "electric shock": "electric_shock",
        "urban flood": "flood",
        "flash flood": "flood",
        "heat wave": "heatwave",
        "heat stroke": "heatwave",
    }

    # ─── Rule patterns (high-confidence shortcuts) ────────────────────────────
    INTENT_PATTERNS = {
        IntentTypes.EMERGENCY: [
            r"\b(help|emergency|sos|trapped|dying|drowning|bleeding|unconscious)\b.*\b(now|immediately|urgent|please)\b",
            r"\b(fire|earthquake|flood|tsunami|cyclone|gas\s*leak|building\s*collapsed?)\b.*\b(now|happening|started|hit)\b",
            # Audit B4: was a bare `\bhelp\s*me\b` which over-fired on benign
            # prompts like "help me with first aid". Now requires co-occurrence
            # of an injury / disaster anchor word.
            r"\bhelp\s*me\b.*\b(trapped|stuck|hurt|injured|bleeding|dying|drowning|choking|burning|fire|earthquake|flood|gas|collapsed|fall(en|ing)?|stroke|attack)\b",
            r"\b(i\s+am|im|i'm)\s+(trapped|stuck|drowning|injured|hurt|bleeding)\b",
            r"\b(someone|people)\s+(is|are)\s+(dying|injured|hurt|trapped|burning)\b",
            r"\bcall\s+(ambulance|police|fire|rescue|edhi|chhipa)\b",
            r"\b(life|death)\s+threatening\b",
            r"\bi\s+want\s+to\s+kill\s+myself\b|\bsuicid",  # crisis routing → emergency
            # Phase 5a: additional crisis-adjacent phrasings the classifier
            # should also catch (the chatbot_service crisis fast-path runs
            # earlier, but defence-in-depth keeps the classifier honest if
            # the fast-path is ever bypassed).
            r"\b(end|ending|going\s+to\s+end)\s+(my|his|her|your)\s+life\b",
        ],
        IntentTypes.GREETINGS: [
            r"^(hi|hello|hey|good\s*(morning|afternoon|evening)|greetings|howdy|salam|salaam|assalam)\b",
            r"^(what'?s?\s+up|sup)\b",
        ],
        IntentTypes.FAREWELL: [
            r"\b(bye|goodbye|see\s+you|take\s+care|good\s*night|thanks?\s+bye)\b",
            r"^(exit|quit|close|end\s+chat)\b",
        ],
        IntentTypes.GRATITUDE: [
            r"\b(thank|thanks|thankyou|thank\s+you|appreciate|grateful|shukria)\b",
            r"\b(helpful|helped|great\s+help)\b",
        ],
        IntentTypes.HELPLINE_QUERY: [
            r"\b(helpline|hotline|emergency\s+number|phone\s+number|contact\s+number)\b",
            r"\b(number|phone|dial)\b.*\b(emergency|police|ambulance|fire|disaster|rescue)\b",
            r"\bwho\s+(to|should\s+i)\s+call\b",
            r"\bwhich\s+number\b",
            r"\b(rescue\s*1122|edhi|chhipa|ndma|pdma)\s*(number|contact)?\b",
            # Phase 5a: "emergency contact(s)" with optional region qualifier
            # ("emergency contacts pakistan", "emergency contact list").
            r"\bemergency\s+contacts?\b",
        ],
        IntentTypes.SHELTER_INFO: [
            r"\b(shelter|evacuation\s+center|safe\s+place|relief\s+camp|refuge)\b",
            r"\bwhere\s+(can|should)\s+i\s+(go|stay|shelter)\b",
            r"\b(nearest|closest|nearby)\s+(shelter|camp|center)\b",
        ],
        IntentTypes.EVACUATION_ROUTE: [
            r"\b(evacuation\s+route|how\s+to\s+evacuate|evacuate\s+(safely|now))\b",
            r"\b(safe\s+route|safe\s+way\s+out|exit\s+plan)\b",
            r"\b(should\s+i\s+leave|do\s+i\s+leave|when\s+to\s+evacuate)\b",
        ],
        IntentTypes.FIRST_AID: [
            r"\b(first\s*aid|cpr|bandage|wound|bleeding|burn|fracture|choking|snake\s*bite|electric\s*shock|heat\s*stroke)\b",
            r"\b(how\s+to)\b.*\b(treat|help|stop|handle)\b.*\b(injury|wound|burn|bleeding|shock)\b",
            r"\b(medical|health)\s+(help|emergency|advice)\b",
            # Phase 5a Fix 2: verb-form + Roman Urdu coverage. The original
            # patterns above used `\bburn\b` / `\bfracture\b`, which fail to
            # match natural phrasings like "burnt my hand" or "fractured arm"
            # because `\b` requires a non-word boundary. These patterns extend
            # the surface to verb tenses and common everyday descriptions.
            r"\b(burn|burnt|burned|burning|scald|scalded|scalding)\b",
            r"\b(broken|fracture|fractured|fractures|sprain|sprained)\s+(arm|leg|wrist|ankle|hand|foot|finger|toe|bone|rib|nose|jaw)?\b",
            r"\b(broken|fractured)\b.*\b(arm|leg|wrist|ankle|hand|foot|finger|toe|bone|rib)\b",
            r"\b(drown|drowned|drowning|swallowed\s+water|aspirat(ed|ion))\b",
            # Roman Urdu often inserts "ka/ko" between subject and verb:
            # "saap ka kaata" / "saap ne kaata" / plain "snake bite".
            r"\b(snake|saap)\s+(ne\s+|ka\s+|ko\s+)?(bite|bit|bitten|kaata|kata|katne)\b|\bsnakebite\b",
            r"\bseizure|seizing|fit\s+pad\s*r?aha?\b",
            r"\banaphylaxis|allergic\s+reaction|severe\s+allerg(y|ic)\b",
            r"\b(diabetic\s+(emergency|attack)|low\s+blood\s+sugar|hypoglyc(a)?em(ia|ic))\b",
            r"\bhypothermia|frostbite|cold\s+injury\b",
            # Whole-message scenarios that map to first-aid even without a
            # canonical "first aid" prefix.
            r"\b(burnt|burned|scalded)\s+(my|his|her|the|a)?\s*(hand|finger|arm|leg|skin|foot|child|baby)\b",
            r"\bchild\s+(swallowed|drowned|burnt|burned|fell|fainted)\b",
            r"\bbaby\s+(swallowed|drowned|burnt|burned|fell|fainted|stopped\s+breathing)\b",
        ],
        IntentTypes.WEATHER_INFO: [
            # Phase 5a.1 Issue 2: WEATHER_INFO matched bare `monsoon` /
            # `rain` and hijacked queries like "what flood risks should I
            # prepare for during monsoon" into the canned weather-data
            # template. WEATHER_INFO is in TEMPLATE_ONLY_INTENTS so this
            # also blocked the LLM path. We chose **Option B** (disaster
            # co-occurrence guard, see _check_rule_patterns) over
            # tightening the regex enumeration: keeping the broad pattern
            # preserves "weather forecast karachi" and "pmd alert"
            # routing, while the guard suppresses the rule when the
            # message ALSO contains a disaster / preparation keyword.
            r"\b(weather|forecast|rain|raining|rains|rainfall|storm|storms|wind|windy|temperature|climate|monsoon)\b",
            r"\b(will\s+it|is\s+it\s+going\s+to)\s+(rain|storm|flood)\b",
            r"\bpmd\b",
        ],
        IntentTypes.REPORT_INCIDENT: [
            # Phase 5a: dropped `tell` from the verb list. "tell me about
            # flood preparedness" is conversational, not reporting; the
            # over-fire was hijacking SAFETY_ADVICE routing for long
            # informational queries. Genuine "tell" reports ("tell the
            # police about a fire I saw") still match via the second
            # pattern below.
            r"\b(report|inform|notify)\b.*\b(incident|accident|disaster|emergency|fire|flood)\b",
            r"\bi\s+(saw|see|witnessed|noticed)\s+(a|an)?\s*(fire|flood|accident|incident|leak|collapse)\b",
            r"\bthere\s+(is|are|has\s+been)\s+(a|an)?\s*(fire|flood|accident|landslide|leak|collapse)\b",
        ],
        IntentTypes.DONATION_VOLUNTEERING: [
            r"\b(donate|donation|donating|volunteer|volunteering)\b",
            r"\b(how\s+can\s+i\s+help|how\s+do\s+i\s+help|want\s+to\s+help)\b.*\b(victims|affected|people|families|relief)\b",
            r"\b(zakat|sadqa|charity|fundraising)\b",
            r"\b(edhi|chhipa|jdc|saylani|al-?khidmat|red\s+crescent|akhuwat)\b",
        ],
        IntentTypes.MENTAL_HEALTH: [
            r"\b(anxiety|anxious|depressed|depression|trauma|ptsd|panic|nightmares?)\b",
            r"\b(mental\s+health|counseling|counselling|therapy|therapist|psychologist|psychiatrist)\b",
            r"\b(can'?t\s+sleep|cannot\s+sleep|sleeplessness|stressed|overwhelmed)\b",
            r"\b(rozan|umang|taskeen)\b",
        ],
    }

    # ─── Disaster sub-intent patterns ─────────────────────────────────────────
    # Phase 5a Fix 2: extended with verb forms + Roman Urdu so the
    # disaster-nudge path catches natural phrasings like "house mein pani aa
    # gaya hai" or "my house is flooding".
    DISASTER_PATTERNS = {
        "earthquake": (
            r"\b(earthquake|earthquakes|quake|seismic|tremor|tremors|"
            r"shaking|aftershock|aftershocks|"
            r"zalzala|bhonchaal|bhunchaal)\b"
        ),
        "flood": (
            r"\b(flood|floods|flooded|flooding|inundation|water\s+level|"
            r"water\s+rising|submerged|monsoon\s+flood|river\s+overflow|"
            r"urban\s+flood|flash\s+flood|"
            r"sailab|seelab|"
            r"pani\s+aa\s+gaya|pani\s+bhar\s+gaya|barish)\b"
        ),
        "heatwave": (
            r"\b(heatwave|heat\s*wave|heat\s*stroke|extreme\s+heat|"
            r"hot\s+weather|loo)\b"
        ),
        "cyclone": (
            r"\b(cyclone|cyclones|hurricane|hurricanes|storm\s+surge|typhoon)\b"
        ),
        "fire": (
            r"\b(fire|burning\s+building|kitchen\s+fire|electrical\s+fire|"
            r"cylinder\s+(fire|explosion)|"
            r"aag(\s+lag\s*g[ae]yi)?)\b"
        ),
        "gas_leak": (
            r"\b(gas\s+leak|gas\s+smell|sui\s+gas|cylinder\s+leak|"
            r"carbon\s+monoxide)\b"
        ),
        "building_collapse": (
            r"\b(building\s+collapsed?|structural\s+collapse|"
            r"wall\s+collapsed?|roof\s+collapsed?|trapped\s+under)\b"
        ),
        "electric_shock": (
            r"\b(electric\s+shock|electrocut(ed|ion)|got\s+shocked|"
            r"live\s+wire|current\s+lag\s*gaya)\b"
        ),
    }

    # ─── Phase 5a Fix 2: broad SAFETY_ADVICE / FIRST_AID rules @ conf 0.75 ───
    # These run AFTER the high-confidence rules (0.85) but BEFORE the ML
    # classifier. They catch verb-form and natural-phrasing queries that
    # don't match the strict patterns above. Confidence is 0.75 — high
    # enough to bypass ML drift, low enough that an explicit emergency or
    # crisis path still wins (those run earlier).
    BROAD_RULE_CONFIDENCE = 0.75
    BROAD_RULE_PATTERNS = {
        IntentTypes.SAFETY_ADVICE: [
            # Anything that mentions a disaster word in a non-emergency
            # framing → safety_advice. The disaster sub_intent is set by
            # _detect_disaster_type via the existing classify() flow.
            r"\b(flood|floods|flooded|flooding|sailab|seelab|"
            r"pani\s+aa\s+gaya|pani\s+bhar\s+gaya|barish|monsoon)\b",
            r"\b(earthquake|earthquakes|quake|tremor|tremors|"
            r"zalzala|bhonchaal|bhunchaal|shaking)\b",
            r"\b(fire|burning|aag(\s+lag\s*g[ae]yi)?)\b",
            r"\b(heatwave|heat\s*wave|extreme\s+heat)\b",
            r"\b(cyclone|hurricane|typhoon)\b",
            r"\b(gas\s+leak|gas\s+smell|sui\s+gas)\b",
            r"\b(building\s+collapse|wall\s+collapse|roof\s+collapse)\b",
            r"\b(electric\s+shock|electrocut(ed|ion))\b",
            # Natural phrasings observed on-device.
            r"\bmy\s+house\s+is\s+flooding\b",
            r"\bhouse\s+mein\s+pani\s+aa\s+gaya\b",
            r"\bwhat\s+(should\s+i\s+do|to\s+do)\s+(if|when|during)?\s*"
            r".*(earthquake|flood|fire|cyclone|heatwave|gas\s+leak)\b",
        ],
    }

    # ─── Training data ────────────────────────────────────────────────────────
    TRAINING_DATA = [
        # SAFETY ADVICE — general
        ("what should I do during an earthquake", IntentTypes.SAFETY_ADVICE),
        ("earthquake safety tips", IntentTypes.SAFETY_ADVICE),
        ("how to stay safe in a flood", IntentTypes.SAFETY_ADVICE),
        ("flood safety guidelines", IntentTypes.SAFETY_ADVICE),
        ("what to do when there is a fire", IntentTypes.SAFETY_ADVICE),
        ("fire safety measures", IntentTypes.SAFETY_ADVICE),
        ("disaster preparedness", IntentTypes.SAFETY_ADVICE),
        ("emergency kit essentials", IntentTypes.SAFETY_ADVICE),
        ("what items to pack for evacuation", IntentTypes.SAFETY_ADVICE),
        ("safety precautions during natural disaster", IntentTypes.SAFETY_ADVICE),
        ("how to protect my family during earthquake", IntentTypes.SAFETY_ADVICE),
        ("how to prepare my home for flood", IntentTypes.SAFETY_ADVICE),
        ("safety guidelines for children during disasters", IntentTypes.SAFETY_ADVICE),
        ("monsoon safety tips", IntentTypes.SAFETY_ADVICE),
        ("heatwave safety tips", IntentTypes.SAFETY_ADVICE),
        ("how to stay safe in heat wave", IntentTypes.SAFETY_ADVICE),
        ("cyclone safety advice for coastal areas", IntentTypes.SAFETY_ADVICE),
        ("gas leak safety", IntentTypes.SAFETY_ADVICE),
        ("building collapse what to do", IntentTypes.SAFETY_ADVICE),
        ("how to stay safe during karachi monsoon", IntentTypes.SAFETY_ADVICE),
        ("urban flooding tips", IntentTypes.SAFETY_ADVICE),
        ("tips for sindh heatwave", IntentTypes.SAFETY_ADVICE),
        ("flash flood safety in gilgit", IntentTypes.SAFETY_ADVICE),

        # HELPLINE QUERY
        ("emergency number", IntentTypes.HELPLINE_QUERY),
        ("what is the helpline for disasters", IntentTypes.HELPLINE_QUERY),
        ("police phone number", IntentTypes.HELPLINE_QUERY),
        ("ambulance contact", IntentTypes.HELPLINE_QUERY),
        ("fire brigade number", IntentTypes.HELPLINE_QUERY),
        ("disaster management helpline", IntentTypes.HELPLINE_QUERY),
        ("who should I call for help", IntentTypes.HELPLINE_QUERY),
        ("emergency contacts pakistan", IntentTypes.HELPLINE_QUERY),
        ("disaster helpline", IntentTypes.HELPLINE_QUERY),
        ("flood control room number", IntentTypes.HELPLINE_QUERY),
        ("rescue 1122 number", IntentTypes.HELPLINE_QUERY),
        ("edhi foundation contact", IntentTypes.HELPLINE_QUERY),
        ("chhipa welfare number", IntentTypes.HELPLINE_QUERY),
        ("ndma helpline", IntentTypes.HELPLINE_QUERY),
        ("pdma punjab number", IntentTypes.HELPLINE_QUERY),
        ("pdma sindh contact", IntentTypes.HELPLINE_QUERY),
        ("sui gas emergency", IntentTypes.HELPLINE_QUERY),
        ("women helpline pakistan", IntentTypes.HELPLINE_QUERY),
        ("child helpline 1098", IntentTypes.HELPLINE_QUERY),
        ("bomb disposal number", IntentTypes.HELPLINE_QUERY),

        # SHELTER
        ("where is the nearest shelter", IntentTypes.SHELTER_INFO),
        ("evacuation center location", IntentTypes.SHELTER_INFO),
        ("relief camp near me", IntentTypes.SHELTER_INFO),
        ("where should I go during flood", IntentTypes.SHELTER_INFO),
        ("safe places during earthquake", IntentTypes.SHELTER_INFO),
        ("how to find emergency shelter", IntentTypes.SHELTER_INFO),
        ("where are people being evacuated to", IntentTypes.SHELTER_INFO),
        ("school turned into relief camp", IntentTypes.SHELTER_INFO),

        # EVACUATION ROUTE
        ("how do I evacuate safely", IntentTypes.EVACUATION_ROUTE),
        ("what's the safe route out", IntentTypes.EVACUATION_ROUTE),
        ("when should I evacuate", IntentTypes.EVACUATION_ROUTE),
        ("evacuation plan for my family", IntentTypes.EVACUATION_ROUTE),
        ("how to leave during a fire", IntentTypes.EVACUATION_ROUTE),
        ("can I drive through flood water", IntentTypes.EVACUATION_ROUTE),
        ("what to take when evacuating", IntentTypes.EVACUATION_ROUTE),
        ("evacuating with elderly parents", IntentTypes.EVACUATION_ROUTE),

        # FIRST AID
        ("how to do CPR", IntentTypes.FIRST_AID),
        ("first aid for burns", IntentTypes.FIRST_AID),
        ("how to stop bleeding", IntentTypes.FIRST_AID),
        ("treatment for fracture", IntentTypes.FIRST_AID),
        ("what to do if someone is choking", IntentTypes.FIRST_AID),
        ("first aid kit contents", IntentTypes.FIRST_AID),
        ("how to treat snake bite", IntentTypes.FIRST_AID),
        ("help for electric shock", IntentTypes.FIRST_AID),
        ("drowning rescue steps", IntentTypes.FIRST_AID),
        ("heat stroke first aid", IntentTypes.FIRST_AID),
        ("what to do when someone faints", IntentTypes.FIRST_AID),
        ("how to treat a deep cut", IntentTypes.FIRST_AID),
        ("severe burn home treatment", IntentTypes.FIRST_AID),

        # WEATHER
        ("weather forecast today", IntentTypes.WEATHER_INFO),
        ("will it rain tomorrow", IntentTypes.WEATHER_INFO),
        ("cyclone alert status", IntentTypes.WEATHER_INFO),
        ("flood warning update", IntentTypes.WEATHER_INFO),
        ("storm prediction for karachi", IntentTypes.WEATHER_INFO),
        ("monsoon forecast pakistan", IntentTypes.WEATHER_INFO),
        ("pmd weather alert", IntentTypes.WEATHER_INFO),

        # REPORT INCIDENT
        ("I want to report a fire", IntentTypes.REPORT_INCIDENT),
        ("there is flooding in my area", IntentTypes.REPORT_INCIDENT),
        ("I saw an accident", IntentTypes.REPORT_INCIDENT),
        ("building collapsed nearby", IntentTypes.REPORT_INCIDENT),
        ("how to report emergency", IntentTypes.REPORT_INCIDENT),
        ("gas pipe leaking on the street", IntentTypes.REPORT_INCIDENT),
        ("there's a wall about to fall", IntentTypes.REPORT_INCIDENT),
        ("I want to report a road accident", IntentTypes.REPORT_INCIDENT),

        # DONATION & VOLUNTEERING
        ("how can I donate to flood victims", IntentTypes.DONATION_VOLUNTEERING),
        ("where to donate for earthquake relief", IntentTypes.DONATION_VOLUNTEERING),
        ("I want to volunteer for disaster relief", IntentTypes.DONATION_VOLUNTEERING),
        ("how to give zakat to flood victims", IntentTypes.DONATION_VOLUNTEERING),
        ("which NGO is best for donation", IntentTypes.DONATION_VOLUNTEERING),
        ("edhi donation account", IntentTypes.DONATION_VOLUNTEERING),
        ("blood donation centers", IntentTypes.DONATION_VOLUNTEERING),
        ("how to help affected families", IntentTypes.DONATION_VOLUNTEERING),
        ("volunteer with red crescent", IntentTypes.DONATION_VOLUNTEERING),

        # MENTAL HEALTH
        ("I feel anxious after the earthquake", IntentTypes.MENTAL_HEALTH),
        ("I can't sleep after the flood", IntentTypes.MENTAL_HEALTH),
        ("nightmares since the disaster", IntentTypes.MENTAL_HEALTH),
        ("post traumatic stress help", IntentTypes.MENTAL_HEALTH),
        ("mental health helpline pakistan", IntentTypes.MENTAL_HEALTH),
        ("counseling after disaster", IntentTypes.MENTAL_HEALTH),
        ("rozan helpline", IntentTypes.MENTAL_HEALTH),
        ("I feel depressed", IntentTypes.MENTAL_HEALTH),
        ("my child is scared after the quake", IntentTypes.MENTAL_HEALTH),

        # GREETINGS
        ("hi", IntentTypes.GREETINGS),
        ("hello", IntentTypes.GREETINGS),
        ("good morning", IntentTypes.GREETINGS),
        ("hey there", IntentTypes.GREETINGS),
        ("salaam", IntentTypes.GREETINGS),
        ("assalamualaikum", IntentTypes.GREETINGS),

        # FAREWELL
        ("bye", IntentTypes.FAREWELL),
        ("goodbye", IntentTypes.FAREWELL),
        ("thanks bye", IntentTypes.FAREWELL),
        ("see you later", IntentTypes.FAREWELL),
        ("good night", IntentTypes.FAREWELL),

        # GRATITUDE
        ("thank you", IntentTypes.GRATITUDE),
        ("thanks for helping", IntentTypes.GRATITUDE),
        ("that was helpful", IntentTypes.GRATITUDE),
        ("I appreciate it", IntentTypes.GRATITUDE),
        ("shukria", IntentTypes.GRATITUDE),

        # FALLBACK
        ("what can you do", IntentTypes.FALLBACK),
        ("who are you", IntentTypes.FALLBACK),
        ("how does this work", IntentTypes.FALLBACK),
        ("random text here", IntentTypes.FALLBACK),
        ("asdfghjkl", IntentTypes.FALLBACK),
        ("tell me a joke", IntentTypes.FALLBACK),
    ]

    # Bumped to v3 when switching solver from liblinear → lbfgs.
    MODEL_FILENAME = "intent_classifier_lr_v3.joblib"

    def __init__(self, model_cache_dir: Optional[str] = None):
        self.model_cache_dir = model_cache_dir or settings.MODEL_CACHE_DIR
        self.ml_classifier: Optional[Pipeline] = None
        self.is_trained = False
        self._initialize_ml_classifier()

    # ─── Initialization ───────────────────────────────────────────────────────
    def _model_path(self) -> str:
        return os.path.join(self.model_cache_dir, self.MODEL_FILENAME)

    def _initialize_ml_classifier(self) -> None:
        """Load from disk if cached, else train and save."""
        path = self._model_path()
        try:
            if os.path.exists(path):
                self.ml_classifier = joblib.load(path)
                self.is_trained = True
                logger.info(f"Loaded intent classifier from {path}")
                return
        except Exception as e:
            logger.warning(f"Failed to load cached classifier: {e} — retraining")

        self._train_and_save()

    def _train_and_save(self) -> None:
        try:
            texts = [t[0] for t in self.TRAINING_DATA]
            labels = [t[1] for t in self.TRAINING_DATA]

            self.ml_classifier = Pipeline(
                [
                    (
                        "tfidf",
                        TfidfVectorizer(
                            ngram_range=(1, 2),
                            max_features=8000,
                            stop_words="english",
                            lowercase=True,
                            min_df=1,
                            sublinear_tf=True,
                        ),
                    ),
                    (
                        "clf",
                        LogisticRegression(
                            class_weight="balanced",
                            max_iter=1000,
                            C=1.5,
                            # lbfgs handles multiclass natively (sklearn 1.8+
                            # deprecates liblinear for multiclass).
                            solver="lbfgs",
                        ),
                    ),
                ]
            )
            self.ml_classifier.fit(texts, labels)
            self.is_trained = True
            logger.info("Intent classifier trained on %d samples", len(texts))

            # Persist
            try:
                os.makedirs(self.model_cache_dir, exist_ok=True)
                joblib.dump(self.ml_classifier, self._model_path())
                logger.info("Persisted intent classifier to %s", self._model_path())
            except Exception as e:
                logger.warning(f"Failed to persist classifier: {e}")
        except Exception as e:
            logger.error(f"Failed to train intent classifier: {e}", exc_info=True)
            self.is_trained = False

    # ─── Public API ───────────────────────────────────────────────────────────
    def classify(self, text: str) -> IntentPrediction:
        """Hybrid classify: rules first, else ML, with disaster-keyword override.

        Phase 5a layered the routing so common bare-noun and verb-form queries
        bypass the ML classifier (which had been over-confident on `fallback`
        for natural phrasings):

            1. Empty check
            2. Short-query disaster shortcut  (Phase 5a Fix 1, conf 0.85)
            3. High-confidence rule patterns (Phase 1+, conf 0.85 / 0.95)
            4. Broad rule patterns           (Phase 5a Fix 2, conf 0.75)
            5. ML classifier                  (existing)
            6. Disaster-keyword nudge         (existing)
            7. Confidence threshold floor     (existing)
        """
        if not text or not text.strip():
            return IntentPrediction(
                intent=IntentTypes.FALLBACK, confidence=0.0, method="empty"
            )

        # 1. Phase 5a Fix 1: short-query disaster shortcut.
        shortcut = self._check_short_query_shortcut(text)
        if shortcut is not None:
            return shortcut

        # 2. High-confidence rule patterns.
        rule = self._check_rule_patterns(text)
        if rule:
            if rule.intent == IntentTypes.SAFETY_ADVICE:
                rule.sub_intent = self._detect_disaster_type(text)
            return rule

        # 3. Phase 5a Fix 2: broad rule patterns at conf 0.75.
        broad = self._check_broad_rule_patterns(text)
        if broad:
            if broad.intent == IntentTypes.SAFETY_ADVICE:
                broad.sub_intent = self._detect_disaster_type(text)
            return broad

        # 4. ML
        ml = self._ml_classify(text)

        # 5. Disaster-keyword nudge — if we see a disaster word and ML wasn't
        #    confident or chose something off, prefer SAFETY_ADVICE.
        disaster_type = self._detect_disaster_type(text)
        if disaster_type and ml.confidence < 0.7:
            return IntentPrediction(
                intent=IntentTypes.SAFETY_ADVICE,
                confidence=max(0.7, ml.confidence),
                sub_intent=disaster_type,
                method="hybrid",
            )

        # 6. Confidence threshold
        if ml.confidence < settings.INTENT_CONFIDENCE_THRESHOLD:
            ml.intent = IntentTypes.FALLBACK

        if ml.intent == IntentTypes.SAFETY_ADVICE and disaster_type:
            ml.sub_intent = disaster_type

        return ml

    # ─── Phase 5a Fix 1: short-query disaster shortcut ──────────────────────
    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in re.split(r"\s+", text.strip().lower()) if t]

    def _check_short_query_shortcut(
        self, text: str
    ) -> Optional[IntentPrediction]:
        """
        Pre-classifier shortcut: if the message is 1-3 tokens AND contains
        exactly one known disaster keyword (English or Roman Urdu, single-
        or multi-word), route directly to SAFETY_ADVICE with that disaster
        as sub_intent at confidence 0.85.

        Examples (all routed to safety_advice with the correct sub_intent):
            "flood"            -> safety_advice + flood
            "fire"             -> safety_advice + fire
            "zalzala"          -> safety_advice + earthquake
            "urban flood"      -> safety_advice + flood (3-token phrase)
            "gas leak"         -> safety_advice + gas_leak (2-token phrase)

        Returns None if the message doesn't qualify (too long, zero or
        multiple disaster matches, etc.) so the regular pipeline takes over.
        """
        lowered = text.strip().lower()
        if not lowered:
            return None
        tokens = self._tokenize(lowered)
        if not (1 <= len(tokens) <= 3):
            return None

        matches: set[str] = set()
        # Single-word matches must be a token (not a substring of another
        # word) — protects against e.g. "fired" in a verbal context.
        for tok in tokens:
            disaster = self._SHORT_QUERY_KEYWORDS_SINGLE.get(tok)
            if disaster:
                matches.add(disaster)
        # Multi-word phrases scanned as substrings.
        for phrase, disaster in self._SHORT_QUERY_KEYWORDS_PHRASES.items():
            if phrase in lowered:
                matches.add(disaster)

        if len(matches) != 1:
            return None
        disaster_type = next(iter(matches))
        return IntentPrediction(
            intent=IntentTypes.SAFETY_ADVICE,
            confidence=0.85,
            sub_intent=disaster_type,
            method="rule_short_query",
        )

    # ─── Phase 5a Fix 2: broad rule patterns @ conf 0.75 ────────────────────
    def _check_broad_rule_patterns(
        self, text: str
    ) -> Optional[IntentPrediction]:
        """
        Catches verb-form / natural phrasings that the strict 0.85 rules
        miss. Lower confidence so a future high-confidence rule (or a
        properly retrained ML) can override.
        """
        text_lower = text.lower()
        for intent, patterns in self.BROAD_RULE_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text_lower, re.IGNORECASE):
                    return IntentPrediction(
                        intent=intent,
                        confidence=self.BROAD_RULE_CONFIDENCE,
                        method="rule_broad",
                    )
        return None

    # ─── Internals ────────────────────────────────────────────────────────────
    # Phase 5a.1 Issue 2: tokens that, when co-occurring with a weather
    # keyword, suppress the WEATHER_INFO rule. The user is asking about
    # flood preparation / earthquake risk / evacuation — not real-time
    # weather data — so the canned weather-data template is wrong. The
    # query falls through to the broader rule layer (which routes to
    # safety_advice + sub_intent) instead.
    _WEATHER_SUPPRESS_TOKENS = (
        "flood", "floods", "flooded", "flooding",
        "earthquake", "quake", "tremor",
        "fire", "burning",
        "cyclone", "hurricane",
        "gas leak", "building collapse", "electric shock",
        "evacuat",          # evacuate / evacuation / evacuated
        "prepare", "preparation", "preparedness",
        "risk", "risks",
        "sailab", "seelab", "zalzala",
        "what should i do",
        "how to stay safe",
    )

    @classmethod
    def _looks_like_weather_query(cls, text_lower: str) -> bool:
        """Return False when a weather keyword co-occurs with a
        disaster/preparation token — that's a safety_advice query, not a
        weather-data query. Returns True only when the message is
        primarily about weather/forecasts."""
        return not any(tok in text_lower for tok in cls._WEATHER_SUPPRESS_TOKENS)

    def _check_rule_patterns(self, text: str) -> Optional[IntentPrediction]:
        text_lower = text.lower()

        # Emergency = highest priority
        for pat in self.INTENT_PATTERNS[IntentTypes.EMERGENCY]:
            if re.search(pat, text_lower, re.IGNORECASE):
                return IntentPrediction(
                    intent=IntentTypes.EMERGENCY, confidence=0.95, method="rule"
                )

        for intent, patterns in self.INTENT_PATTERNS.items():
            if intent == IntentTypes.EMERGENCY:
                continue
            for pat in patterns:
                if re.search(pat, text_lower, re.IGNORECASE):
                    # Phase 5a.1 Issue 2 — suppress WEATHER_INFO when the
                    # message also contains a disaster/preparation token.
                    if (
                        intent == IntentTypes.WEATHER_INFO
                        and not self._looks_like_weather_query(text_lower)
                    ):
                        continue
                    return IntentPrediction(
                        intent=intent, confidence=0.85, method="rule"
                    )
        return None

    def _detect_disaster_type(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for disaster_type, pat in self.DISASTER_PATTERNS.items():
            if re.search(pat, text_lower, re.IGNORECASE):
                return disaster_type
        return None

    def _ml_classify(self, text: str) -> IntentPrediction:
        if not self.is_trained or self.ml_classifier is None:
            return IntentPrediction(
                intent=IntentTypes.FALLBACK, confidence=0.0, method="fallback"
            )
        try:
            proba = self.ml_classifier.predict_proba([text])[0]
            classes = self.ml_classifier.classes_
            idx = int(np.argmax(proba))
            return IntentPrediction(
                intent=classes[idx],
                confidence=float(proba[idx]),
                method="ml",
            )
        except Exception as e:
            logger.error(f"ML classification failed: {e}")
            return IntentPrediction(
                intent=IntentTypes.FALLBACK, confidence=0.0, method="fallback"
            )

    def get_confidence_explanation(self, prediction: IntentPrediction) -> str:
        c = prediction.confidence
        if c >= 0.9:
            return "Very high confidence"
        if c >= 0.75:
            return "High confidence"
        if c >= 0.6:
            return "Moderate confidence"
        if c >= 0.4:
            return "Low confidence"
        return "Very low confidence — using fallback"


# ─── Singleton ────────────────────────────────────────────────────────────────
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
