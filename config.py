"""
Configuration settings for the SafeLink Safety Chatbot.

All settings can be overridden via environment variables (see .env.example).
Pydantic-Settings reads .env on local dev and inherits process env on Railway.
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings — env-driven."""

    # ─── Server ───────────────────────────────────────────────────────────────
    APP_NAME: str = "SafeLink Safety Chatbot"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    # Railway injects $PORT — read it lazily so we don't hard-code 8000 in prod.
    PORT: int = int(os.environ.get("PORT", 8000))

    API_PREFIX: str = "/api/v1"

    # ─── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated env (e.g., "https://app.example.com,https://staging.example.com").
    # If unset, falls back to a dev-safe list (localhost + Android emulator host
    # loopback). Setting "*" is still accepted but disables credentials at the
    # middleware layer (see main.py) per CORS spec.
    CORS_ORIGINS: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw:
            return ["http://localhost", "http://10.0.2.2"]
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        """Browsers reject `*` + credentials. Only allow credentials when the
        origins are concretely listed."""
        return self.cors_origin_list != ["*"]

    # ─── NLP ──────────────────────────────────────────────────────────────────
    USE_EMBEDDINGS: bool = False
    USE_SPACY: bool = False
    SPACY_MODEL: str = "en_core_web_sm"
    SENTENCE_TRANSFORMER_MODEL: str = "all-MiniLM-L6-v2"

    INTENT_CONFIDENCE_THRESHOLD: float = 0.55
    # TF-IDF cosine on short queries (1-3 content words) lands ~0.15-0.30,
    # so the runtime default is 0.15 to avoid empty retrievals. Keep
    # .env.example in sync — the prior 0.25 value there was misleading.
    RETRIEVAL_SCORE_THRESHOLD: float = 0.15
    TOP_K_RESULTS: int = 3

    # Where to persist the trained intent classifier between cold starts.
    # Railway: /tmp survives within a deploy; mount a volume for true persistence.
    MODEL_CACHE_DIR: str = "/tmp/safelink_chatbot"

    # ─── Emergency Keywords ───────────────────────────────────────────────────
    # Bare "help" and bare "emergency" intentionally REMOVED — they over-fired
    # for benign queries like "help me with first aid" or "emergency numbers".
    # The keyword-set trigger now requires urgency_score >= 0.6 AND >= 1
    # keyword overlap (see chatbot_service._check_emergency).
    EMERGENCY_KEYWORDS: str = (
        "trapped,dying,drowning,bleeding,unconscious,"
        "earthquake now,flood now,fire now,gas leak,collapsed,"
        "heart attack,suicide"
    )

    # ─── Database / Redis (optional — currently unused) ───────────────────────
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # ─── Privacy & Logging ────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ANONYMIZE_LOGS: bool = True
    LOG_RETENTION_DAYS: int = 30

    # ─── Auth ─────────────────────────────────────────────────────────────────
    # Required when DEBUG=False. In DEBUG=True mode the auth dependency accepts
    # any (or missing) X-API-Key header — see services/auth.py.
    CHATBOT_API_KEY: str = ""

    # ─── Rate Limiting (slowapi, per-IP) ──────────────────────────────────────
    RATE_LIMIT_CHAT_PER_MIN: int = 30
    RATE_LIMIT_FEEDBACK_PER_MIN: int = 5
    # Legacy fields retained for API stability; not enforced.
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW: int = 60

    # ─── Feedback log ─────────────────────────────────────────────────────────
    # Empty → resolved to chatbot_backend/data/feedback.jsonl by feedback_log.py.
    # Set to a writable, persistent path (mounted volume) in production.
    FEEDBACK_LOG_PATH: str = ""

    # ─── Region ───────────────────────────────────────────────────────────────
    # Pakistan-first; the helplines.json `aliases` map handles fallback.
    DEFAULT_REGION: str = "pakistan"

    # ─── Phase 3: Hybrid LLM ──────────────────────────────────────────────────
    # USE_LLM is the single feature flag. Default False — production runs the
    # legacy pipeline unchanged until explicitly enabled per Railway env var.
    USE_LLM: bool = False
    LLM_PRIMARY: str = "gemini"
    LLM_FALLBACK: str = "groq"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TIMEOUT_SECONDS: float = 12.0
    LLM_FALLBACK_TIMEOUT_SECONDS: float = 8.0
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 800
    LLM_MAX_TOOL_ROUNDS: int = 3

    # ─── Phase 3: Sessions ────────────────────────────────────────────────────
    SESSION_TTL_MINUTES: int = 30
    SESSION_MAX_TURNS: int = 6
    # Locked: 1000 default sized for Railway Hobby tier (~512 MB RAM).
    # Override on Pro / higher tiers — see RAILWAY_SETUP.md (Phase 5).
    SESSION_MAX_ACTIVE: int = 1000
    SESSION_SWEEP_INTERVAL_SECONDS: int = 300

    # ─── Phase 3: Output validator ────────────────────────────────────────────
    ALLOWED_LINK_DOMAINS: str = (
        "ndma.gov.pk,pmd.gov.pk,who.int,prcs.org.pk,redcrescent.pk,"
        "edhi.org,rescue.gov.pk,heart.org,redcross.org,rozan.org,"
        "umang.com.pk,taskeen.org,ssgc.com.pk,sngpl.com.pk,gsp.gov.pk,"
        "usgs.gov"
    )
    OUTPUT_MAX_CHARS: int = 1500

    @property
    def allowed_link_domain_list(self) -> List[str]:
        return [d.strip() for d in (self.ALLOWED_LINK_DOMAINS or "").split(",") if d.strip()]

    # ─── Phase 3: Offline bundle cache ────────────────────────────────────────
    OFFLINE_BUNDLE_TTL_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached settings — built once per process."""
    return Settings()


# ─── Intent Categories ────────────────────────────────────────────────────────
class IntentTypes:
    SAFETY_ADVICE = "safety_advice"
    HELPLINE_QUERY = "helpline_query"
    SHELTER_INFO = "shelter_info"
    EVACUATION_ROUTE = "evacuation_route"
    FIRST_AID = "first_aid"
    WEATHER_INFO = "weather_info"
    REPORT_INCIDENT = "report_incident"
    EMERGENCY = "emergency"
    DONATION_VOLUNTEERING = "donation_volunteering"
    MENTAL_HEALTH = "mental_health"
    GREETINGS = "greetings"
    FAREWELL = "farewell"
    GRATITUDE = "gratitude"
    FALLBACK = "fallback"

    @classmethod
    def all(cls) -> List[str]:
        return [
            cls.SAFETY_ADVICE,
            cls.HELPLINE_QUERY,
            cls.SHELTER_INFO,
            cls.EVACUATION_ROUTE,
            cls.FIRST_AID,
            cls.WEATHER_INFO,
            cls.REPORT_INCIDENT,
            cls.EMERGENCY,
            cls.DONATION_VOLUNTEERING,
            cls.MENTAL_HEALTH,
            cls.GREETINGS,
            cls.FAREWELL,
            cls.GRATITUDE,
            cls.FALLBACK,
        ]


# ─── Disaster Types ───────────────────────────────────────────────────────────
class DisasterTypes:
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    HEATWAVE = "heatwave"
    CYCLONE = "cyclone"
    FIRE = "fire"
    GAS_LEAK = "gas_leak"
    BUILDING_COLLAPSE = "building_collapse"
    GENERAL = "general"

    @classmethod
    def all(cls) -> List[str]:
        return [
            cls.EARTHQUAKE,
            cls.FLOOD,
            cls.HEATWAVE,
            cls.CYCLONE,
            cls.FIRE,
            cls.GAS_LEAK,
            cls.BUILDING_COLLAPSE,
            cls.GENERAL,
        ]


# ─── Response Templates (string fallbacks if data/response_templates.json missing) ──
EMERGENCY_RESPONSE_TEMPLATE = """
🚨 **EMERGENCY DETECTED**

**If you are in immediate danger:**
1. Call emergency services immediately: **{emergency_number}**
2. Stay calm and follow instructions from emergency responders
3. If safe to do so, move to a secure location

{specific_guidance}

**Emergency Helplines:**
{helplines}
"""

SAFETY_ADVICE_TEMPLATE = """
**{disaster_type} Safety Guidance**

{safety_steps}

**Important Contacts:**
{helplines}

⚠️ *If this is a life-threatening emergency, call {emergency_number} immediately.*
"""

HELPLINE_TEMPLATE = """
**Emergency Helplines:**

{helplines}

💡 *Save these numbers for quick access during emergencies.*
"""

FALLBACK_TEMPLATE = """
I'm not entirely sure about your specific query, but here's some general guidance:

{guidance}

**For immediate assistance:**
{helplines}

*If you need specific information, please try rephrasing your question or specify the type of disaster/emergency you're asking about.*
"""

FIRST_AID_DISCLAIMER = (
    "⚠️ **Medical Disclaimer:** This is basic first-aid guidance only. For "
    "serious injuries or medical emergencies, call **115** or **1122** "
    "immediately. Do not attempt procedures beyond your training."
)
