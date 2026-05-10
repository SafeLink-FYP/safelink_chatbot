"""
Pydantic models for API request/response validation.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum


def _utcnow() -> datetime:
    """Timezone-aware UTC now. Replaces datetime.utcnow() (deprecated 3.12+)."""
    return datetime.now(timezone.utc)


class MessageType(str, Enum):
    USER = "user"
    BOT = "bot"
    SYSTEM = "system"


class UrgencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─── Request Models ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    """Incoming chat message from user."""
    message: str = Field(..., min_length=1, max_length=2000, description="User's message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation tracking")
    user_id: Optional[str] = Field(None, description="Anonymous user identifier")
    region: Optional[str] = Field("pakistan", description="User's region for localized helplines")
    province: Optional[str] = Field(None, description="User's province (punjab, sindh, kpk, balochistan, gilgit_baltistan, ajk, islamabad)")
    city: Optional[str] = Field(None, description="User's city — used to derive province if province not given")
    language: Optional[str] = Field("en", description="Preferred language code")
    location: Optional[Dict[str, float]] = Field(None, description="User's coordinates {lat, lng}")
    offline_context: Optional[bool] = Field(False, description="Whether user is in offline mode")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "What should I do during an earthquake?",
                "session_id": "sess_123456",
                "region": "pakistan",
                "city": "islamabad",
                "language": "en",
            }
        }
    )


class FeedbackRequest(BaseModel):
    """User feedback on a bot response."""
    message_id: str = Field(..., description="ID of the message being rated")
    session_id: Optional[str] = Field(None, description="Session ID")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating from 1-5")
    feedback_text: Optional[str] = Field(None, max_length=500, description="Optional feedback text")
    helpful: bool = Field(..., description="Whether the response was helpful")
    comment: Optional[str] = Field(None, max_length=500, description="Free-text comment from the user")


class ReportIncidentRequest(BaseModel):
    """User reporting an incident."""
    incident_type: str = Field(..., description="Type of incident/disaster")
    description: str = Field(..., max_length=1000)
    location: Optional[Dict[str, float]] = None
    address: Optional[str] = None
    severity: Optional[UrgencyLevel] = UrgencyLevel.MEDIUM
    contact_number: Optional[str] = None


# ─── Response Models ──────────────────────────────────────────────────────────
class IntentResult(BaseModel):
    intent: str
    confidence: float
    sub_intent: Optional[str] = None


class EntityResult(BaseModel):
    entity_type: str
    value: str
    confidence: float
    start: int
    end: int


class HelplineInfo(BaseModel):
    name: str
    number: str
    description: Optional[str] = None
    available_24x7: bool = True
    region: str


class SourceCitation(BaseModel):
    """Phase 3 — citation surfaced to the client when the response is
    grounded in a KB entry. Url is optional (some sources are name-only)."""
    name: str
    url: Optional[str] = None


class SafetyStep(BaseModel):
    step_number: int
    action: str
    details: Optional[str] = None
    is_critical: bool = False


class GuidanceContent(BaseModel):
    """Disaster guidance content. All step lists are optional so we can ship
    summary-only entries without coercion."""
    disaster_type: str
    title: str
    summary: str = ""
    before_steps: List[SafetyStep] = []
    during_steps: List[SafetyStep] = []
    after_steps: List[SafetyStep] = []
    warnings: List[str] = []
    helpful_links: List[str] = []


class ChatResponse(BaseModel):
    """Bot response to user message."""
    message_id: str
    response: str
    response_type: str
    intent: IntentResult
    entities: List[EntityResult] = []
    helplines: List[HelplineInfo] = []
    urgency_level: UrgencyLevel = UrgencyLevel.LOW
    suggested_actions: List[str] = []
    related_topics: List[str] = []
    confidence_score: float = Field(..., ge=0, le=1)
    is_emergency: bool = False
    offline_available: bool = True
    region: Optional[str] = None
    province: Optional[str] = None
    timestamp: datetime = Field(default_factory=_utcnow)
    # Phase 3 additive fields. Backwards compatible — Dart client falls back
    # to defaults when the backend hasn't populated them (legacy pipeline).
    sources: List[SourceCitation] = []
    used_llm: bool = False


class ChatStreamChunk(BaseModel):
    """SSE wire format for /api/v1/chat/stream. The client accumulates
    `delta` text until `done=true`, then renders the metadata fields."""
    message_id: str
    delta: str = ""
    done: bool = False
    sources: Optional[List[SourceCitation]] = None
    helplines: Optional[List[HelplineInfo]] = None
    suggested_actions: Optional[List[str]] = None
    used_llm: bool = False
    provider_used: Optional[str] = None
    error: Optional[str] = None


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    services: Dict[str, str]


class OfflineDataResponse(BaseModel):
    """Offline data package for the mobile app to cache.

    NOTE: Field is `quick_tips` (renamed from `common_responses` in v2.0). The
    Flutter client expects the JSON key `quick_tips` — keep them in sync.
    """
    version: str
    last_updated: datetime
    guidance_data: List[GuidanceContent] = []
    helplines: Dict[str, List[HelplineInfo]] = {}
    quick_tips: Dict[str, str] = {}
    emergency_keywords: List[str] = []
    checksum: str


class ConversationHistory(BaseModel):
    message_id: str
    session_id: str
    user_message: str
    bot_response: str
    intent: str
    timestamp: datetime
    feedback_rating: Optional[int] = None


class ErrorResponse(BaseModel):
    error: str
    error_code: str
    message: str
    timestamp: datetime = Field(default_factory=_utcnow)
