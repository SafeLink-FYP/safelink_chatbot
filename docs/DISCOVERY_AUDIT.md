# SafeLink Chatbot — Discovery Audit

**Date:** 2026-05-07
**Mode:** Read-only. No code edits, no recommendations, no architecture proposals.
**Scope:** `safelink/lib/features/chatbot/`, `safelink/chatbot_backend/`, and chatbot-touching pieces of `safelink/lib/core/`.

---

## A. Backend — schemas & contracts

### A1. `ChatRequest` and `ChatResponse` (paste from `chatbot_backend/models/schemas.py`)

```python
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
```

```python
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
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

Supporting models referenced by `ChatResponse`:

```python
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

class UrgencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

### A2. One representative KB entry (`data/knowledge_base.json`)

```json
{
  "id": "earthquake_during_1",
  "disaster_type": "earthquake",
  "category": "during",
  "title": "Earthquake Safety — During the Shaking",
  "content": "**DROP, COVER, and HOLD ON!**\n\n1. **DROP** to your hands and knees immediately\n2. **COVER** your head and neck under a sturdy desk or table\n3. **HOLD ON** until the shaking stops\n\n**If Indoors:**\n- Stay inside — don't run outside during shaking; falling debris in narrow lanes is the biggest killer\n- Stay away from windows, outside walls, and anything heavy that could topple (almirahs, TVs)\n- If no shelter is available, crouch near an interior wall and protect your head\n\n**If Outdoors:**\n- Move to a clear area away from buildings, electricity poles, billboards, and trees\n- Drop to the ground and protect your head\n\n**If in a Vehicle:**\n- Pull over safely and stop\n- Stay inside with your seatbelt fastened\n- Avoid stopping near buildings, overpasses, flyovers, or power lines\n\n**Do NOT:**\n- Run outside during shaking\n- Stand in doorways (Pakistani RCC frame doorways are NOT inherently safer)\n- Use elevators\n\n**Emergency Contacts:**\n- Rescue 1122\n- Edhi: 115",
  "searchable_text": "earthquake what to do during earthquake safety drop cover hold shaking tremor seismic indoors outdoors vehicle",
  "source": "NDMA Pakistan; USGS public guidance",
  "metadata": {"verified": true, "last_updated": "2026-04"}
}
```

The file is a flat JSON **array** of these objects. Top-level keys per entry: `id`, `disaster_type`, `category`, `title`, `content`, `searchable_text`, `source`, `metadata`. `metadata` observed sub-keys: `verified`, `last_updated`, `disclaimer`.

### A3. One province block (`data/helplines.json`)

```json
"punjab": {
  "label": "Punjab",
  "pdma": {
    "name": "PDMA Punjab",
    "number": "042-99205316",
    "description": "Provincial Disaster Management Authority — Punjab",
    "category": "disaster"
  },
  "rescue": "1122",
  "major_cities": ["lahore", "faisalabad", "rawalpindi", "multan", "gujranwala", "sialkot", "bahawalpur", "sargodha", "sheikhupura", "rahim yar khan", "jhang", "kasur", "okara", "sahiwal", "wah cantt", "dera ghazi khan", "gujrat", "chakwal", "attock", "jhelum", "mandi bahauddin", "mianwali", "khanewal"]
}
```

Top-level structure of `helplines.json`: `{version, last_updated, country, primary_region_key, category_priorities, regions: {pakistan: {country, emergency_number, alt_emergency_number, helplines[], provinces: {<province>: {...}}}}, aliases, quick_reference}`.

A nationwide helpline entry (inside `regions.pakistan.helplines`):

```json
{
  "name": "Rescue 1122",
  "number": "1122",
  "description": "Punjab/KPK Emergency Service — Rescue, Medical, Fire (also operates in parts of Sindh, Balochistan, AJK, GB)",
  "available_24x7": true,
  "category": "emergency"
}
```

### A4. KB entry count and breakdown

**Total: 27 entries.**

| `disaster_type` | count |
|---|---|
| earthquake | 4 |
| flood | 5 |
| heatwave | 1 |
| cyclone | 1 |
| fire | 1 |
| gas_leak | 1 |
| building_collapse | 1 |
| general | 13 |
| **total** | **27** |

By `category` (the file's pseudo-phase facet):

| `category` | count |
|---|---|
| during | 6 |
| before | 3 |
| after | 2 |
| first_aid | 10 |
| general | 6 |

The 13 `general`-typed entries are: 9 `first_aid` first-aid entries (bleeding, cpr, burns, snake_bite, electric_shock, drowning, heat_stroke, choking, fracture), 1 `before` (general_kit_1), 1 `first_aid` (mental_health_post_disaster_1), 1 `general` (evacuation_general_1), 1 `general` (donation_volunteering_general_1).

Entry IDs (full list):
```
earthquake_during_1, earthquake_before_1, earthquake_after_1, earthquake_zones_pk,
flood_during_1, flood_before_1, flood_after_1, flood_urban_1, flood_flash_1,
heatwave_1, cyclone_1, fire_1, gas_leak_1, building_collapse_1,
first_aid_bleeding_1, first_aid_cpr_1, first_aid_burns_1, first_aid_snake_bite_1,
first_aid_electric_shock_1, first_aid_drowning_1, first_aid_heat_stroke_1,
first_aid_choking_1, first_aid_fracture_1,
general_kit_1, mental_health_post_disaster_1,
evacuation_general_1, donation_volunteering_general_1
```

### A5. Helpline counts

- **Nationwide helplines** (`regions.pakistan.helplines`): **21 entries**.
- **Provincial PDMA entries**: 7 (one per `provinces.<province>.pdma`: punjab, sindh, kpk, balochistan, gilgit_baltistan, ajk, islamabad).
- **Total numbers in file** (grep `"number":`): 28.
- **District-level numbers**: none. No district granularity anywhere.
- **Hospital-level numbers**: 2 in the nationwide list — Aga Khan University Hospital (Karachi) and Shaukat Khanum Hospital (Lahore).
- **Per-entry `verified_at` / `verified_by` timestamps**: none.

---

## B. Backend — configuration

### B6. `Settings` class (paste from `chatbot_backend/config.py`)

```python
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
    # "*" allows any origin (suitable only for dev / pure mobile clients).
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ─── NLP ──────────────────────────────────────────────────────────────────
    USE_EMBEDDINGS: bool = False
    USE_SPACY: bool = False
    SPACY_MODEL: str = "en_core_web_sm"
    SENTENCE_TRANSFORMER_MODEL: str = "all-MiniLM-L6-v2"

    INTENT_CONFIDENCE_THRESHOLD: float = 0.55
    # TF-IDF cosine on short queries (1-3 content words) lands ~0.15-0.30,
    # so keep this conservative to avoid empty retrievals.
    RETRIEVAL_SCORE_THRESHOLD: float = 0.15
    TOP_K_RESULTS: int = 3

    # Where to persist the trained intent classifier between cold starts.
    # Railway: /tmp survives within a deploy; mount a volume for true persistence.
    MODEL_CACHE_DIR: str = "/tmp/safelink_chatbot"

    # ─── Emergency Keywords ───────────────────────────────────────────────────
    EMERGENCY_KEYWORDS: str = (
        "help,emergency,trapped,dying,drowning,bleeding,unconscious,"
        "earthquake now,flood now,sos,fire now,gas leak,collapsed,"
        "heart attack,suicide"
    )

    # ─── Database / Redis (optional — currently unused) ───────────────────────
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # ─── Privacy & Logging ────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ANONYMIZE_LOGS: bool = True
    LOG_RETENTION_DAYS: int = 30

    # ─── Rate Limiting (informational — not enforced yet) ─────────────────────
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW: int = 60

    # ─── Region ───────────────────────────────────────────────────────────────
    # Pakistan-first; the helplines.json `aliases` map handles fallback.
    DEFAULT_REGION: str = "pakistan"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )
```

### B7. `.env.example` contents

```
# SafeLink Safety Chatbot — Environment Configuration
# Copy this file to .env locally; on Railway set these as project variables.

# ───── Server ─────────────────────────────────────────────────────────────────
APP_NAME=SafeLink Safety Chatbot
APP_VERSION=2.0.0
DEBUG=false
HOST=0.0.0.0
# Railway injects $PORT automatically — do NOT hard-code this on Railway.
PORT=8000

# API base path
API_PREFIX=/api/v1

# ───── CORS ───────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins. Use * for open access (dev only).
# Production example:
#   CORS_ORIGINS=https://safelink.example.com,https://staging.safelink.example.com
CORS_ORIGINS=*

# ───── NLP ────────────────────────────────────────────────────────────────────
# Keyword + TF-IDF retrieval is the default and what's bundled in requirements.txt.
USE_EMBEDDINGS=false
USE_SPACY=false
SPACY_MODEL=en_core_web_sm
SENTENCE_TRANSFORMER_MODEL=all-MiniLM-L6-v2

INTENT_CONFIDENCE_THRESHOLD=0.55
RETRIEVAL_SCORE_THRESHOLD=0.25
TOP_K_RESULTS=3

# Path where the trained intent classifier is persisted between cold starts.
# On Railway, /tmp survives within a deploy; for permanent caching mount a volume.
MODEL_CACHE_DIR=/tmp/safelink_chatbot

# ───── Emergency Keywords ─────────────────────────────────────────────────────
# Comma-separated. These trigger the emergency fast-path response.
EMERGENCY_KEYWORDS=help,emergency,trapped,dying,drowning,bleeding,unconscious,earthquake now,flood now,sos,fire now,gas leak,collapsed,heart attack,suicide

# ───── Privacy & Logging ──────────────────────────────────────────────────────
LOG_LEVEL=INFO
ANONYMIZE_LOGS=true
LOG_RETENTION_DAYS=30

# ───── Rate Limiting (informational — currently not enforced) ─────────────────
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW=60

# ───── Region ─────────────────────────────────────────────────────────────────
DEFAULT_REGION=pakistan

# ───── Optional Database / Redis (currently unused) ───────────────────────────
# DATABASE_URL=postgresql://user:password@host:5432/safelink_chatbot
# REDIS_URL=redis://host:6379/0
```

> Note: `.env.example` documents `RETRIEVAL_SCORE_THRESHOLD=0.25` while `config.py` defaults to `0.15`. The runtime code is authoritative; the example file is out of sync.

### B8. CORS loading & default

- Env var name: `CORS_ORIGINS`. Single comma-separated string.
- Default: `"*"`.
- Parsed via the `cors_origin_list` property: empty/`"*"` → `["*"]`, else split on commas + strip.
- Wired in `main.py:77–83`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_credentials=True` is unconditional, including when `allow_origins=["*"]`.

### B9. Feedback log path

Hardcoded relative path in `routers/chat_router.py:28–30`:

```python
FEEDBACK_LOG = os.path.join(
    os.path.dirname(__file__), "..", "data", "feedback.jsonl"
)
```

No env var override. The path resolves relative to the chat_router.py file's location. The directory is created at write time with `os.makedirs(...exist_ok=True)`. The file is `.gitignore`d (`data/feedback.jsonl` line 25).

---

## C. Backend — endpoints & deployment

### C10. Registered routes

From `main.py`:

| Method | Path | Purpose |
|---|---|---|
| GET  | `/`        | Service banner / metadata JSON |
| GET  | `/health`  | Lightweight liveness — does **not** instantiate the chatbot service |
| GET  | `/ready`   | Readiness — calls `get_chatbot_service()` to confirm the NLP pipeline is loaded |

From `routers/chat_router.py` (mounted at `/api/v1` via `settings.API_PREFIX`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/chat/message`           | Main chat endpoint — runs `process_message` and returns `ChatResponse` |
| POST | `/api/v1/chat/feedback`          | Append feedback record to `feedback.jsonl` |
| GET  | `/api/v1/chat/helplines/{region}` | Province- and category-filtered helpline list |
| GET  | `/api/v1/chat/offline-data`      | Builds the cacheable offline bundle (helplines, quick_tips, emergency_keywords, guidance summary, sha256 checksum) |
| GET  | `/api/v1/chat/quick-tip/{disaster_type}` | Single quick-tip card for the disaster type |
| GET  | `/api/v1/chat/intents`           | Introspection — list of supported intents |
| GET  | `/api/v1/chat/disasters`         | Introspection — list of supported disaster types |

Middleware: per-request structured logger + global `Exception` handler returning 500 with a fixed JSON body. No auth dependency, no rate-limit middleware.

### C11. Deployed Railway URL

**Not deployed.** Repo-wide grep finds no Railway URL, no production domain, no staging URL. The only `railway.app` hit is the schema URL in `railway.json`. The only `safelink.example.com` reference is a placeholder comment in `.env.example`. The Flutter client points to `http://10.0.2.2:8000/api/v1` (Android emulator host loopback).

### C12. `railway.json` healthcheck

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

Healthcheck path: `/health`.

### C13. `requirements.txt`

```
# SafeLink Safety Chatbot — Python Dependencies
# Pinned for stable Railway deployment (Python 3.11)
# Install: pip install -r requirements.txt

# Web Framework
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
pydantic-settings==2.5.2

# HTTP client (used in tests / health probes)
httpx==0.27.2

# NLP & ML — keyword + TF-IDF retrieval (no embeddings required)
scikit-learn==1.5.2
numpy==1.26.4
joblib==1.4.2

# Utilities
python-multipart==0.0.10
python-dotenv==1.0.1

# ── OPTIONAL — uncomment if you want semantic-embedding retrieval ────────────
# Adds ~500 MB memory + ~100 MB download. Likely too heavy for Railway free tier.
# sentence-transformers==2.7.0

# ── OPTIONAL — uncomment for richer NER ──────────────────────────────────────
# After install: python -m spacy download en_core_web_sm
# spacy==3.7.6

# ── OPTIONAL — Database / cache (currently unused) ───────────────────────────
# sqlalchemy==2.0.35
# asyncpg==0.30.0
# redis==5.1.1

# Development
pytest==8.3.3
pytest-asyncio==0.24.0
```

Active deps: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `httpx`, `scikit-learn`, `numpy`, `joblib`, `python-multipart`, `python-dotenv`, `pytest`, `pytest-asyncio`. No `slowapi`, no LLM SDKs, no `sentence-transformers`, no `spacy` enabled.

---

## D. Frontend — conventions

### D14. `AppSecrets` (full file paste)

`safelink/lib/core/secrets/app_secrets.dart`:

```dart
import 'dart:io';

class AppSecrets {
  static const String supabaseUrl = 'https://eoixpffqoygzasyuvahl.supabase.co';
  static const String supabaseAnonKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVvaXhwZmZxb3lnemFzeXV2YWhsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAyMjcyNTcsImV4cCI6MjA3NTgwMzI1N30.HUapK_UmzBSknNnYNS9je9DbwpGMKtOI9aa5dy8b-Zc';

  // Web OAuth Client ID from Google Cloud Console — NOT the Android client.
  // Android Google Sign-In uses this as the `serverClientId`; the issued ID
  // token's audience is this value, and Supabase verifies tokens against it.
  // The same Web Client ID must be configured in Supabase Auth → Providers →
  // Google. The Android calling app is identified by SHA-1 fingerprint +
  // package name registered in the GCP OAuth consent screen.
  //
  // Replace the placeholder below with your real Web Client ID.
  static const String googleWebClientId = '115346446790-0fo3ib6o3knromlqu6oo456ua39okhe5.apps.googleusercontent.com';

  static bool get isGoogleSignInConfigured =>
      !googleWebClientId.startsWith('REPLACE_WITH_');

  static String get mlApiBaseUrl {
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }
}
```

Style: `static const` literal strings + one platform-aware getter (`mlApiBaseUrl`). No `--dart-define` reads, no `String.fromEnvironment`. Real production secrets are committed as constants. No `chatbotBaseUrl` field exists; the chatbot has its own hardcoded URL inside `chatbot_remote_service.dart:6`.

### D15. `InitialBindings` registration pattern (full file paste)

`safelink/lib/core/di/initial_bindings.dart`:

```dart
import 'package:get/get.dart';
import 'package:safelink/features/alerts/controllers/alert_controller.dart';
import 'package:safelink/features/dashboard/controllers/ml_alert_controller.dart';
import 'package:safelink/features/dashboard/services/ml_alert_service.dart';
import 'package:safelink/features/authorization/data/repositories/auth_repository.dart';
import 'package:safelink/features/authorization/controllers/auth_controller.dart';
import 'package:safelink/features/authorization/controllers/image_picking_controller.dart';
import 'package:safelink/features/authorization/services/auth_service.dart';
import 'package:safelink/features/aid/controllers/s_o_s_controller.dart';
import 'package:safelink/features/cases/services/case_tracking_service.dart';
import 'package:safelink/features/aid/services/disaster_report_service.dart';
import 'package:safelink/features/aid/services/s_o_s_service.dart';
import 'package:safelink/features/alerts/services/alert_service.dart';
import 'package:safelink/features/chatbot/data/repositories/chatbot_repository.dart';
import 'package:safelink/features/chatbot/services/chatbot_service.dart';
import 'package:safelink/features/notifications/controllers/notification_controller.dart';
import 'package:safelink/features/notifications/services/notification_service.dart';
import 'package:safelink/features/settings/services/settings_service.dart';
import 'package:safelink/features/profile/controllers/profile_controller.dart';
import 'package:safelink/features/profile/services/profile_services.dart';
import 'package:safelink/features/preparedness/data/repositories/preparedness_repository.dart';
import 'package:safelink/features/preparedness/services/preparedness_state_service.dart';
import 'package:safelink/features/preparedness/controllers/preparedness_controller.dart';
import 'package:safelink/shared/controllers/emergency_contact_controller.dart';

class InitialBindings extends Bindings {
  @override
  void dependencies() {
    /// SERVICES
    Get.put<AuthService>(AuthService(), permanent: true);
    Get.put<AuthRepository>(
      AuthRepository(Get.find<AuthService>()),
      permanent: true,
    );
    Get.put<ProfileService>(ProfileService(), permanent: true);
    Get.put<SOSService>(SOSService(), permanent: true);
    Get.put<NotificationService>(NotificationService(), permanent: true);
    Get.put<AlertService>(AlertService(), permanent: true);
    Get.put<SettingsService>(SettingsService(), permanent: true);
    Get.put<CaseTrackingService>(CaseTrackingService(), permanent: true);
    Get.put<DisasterReportService>(DisasterReportService(), permanent: true);
    Get.put<ChatbotRepository>(ChatbotRepository(), permanent: true);
    Get.put<ChatbotService>(
      ChatbotService(repository: Get.find<ChatbotRepository>()),
      permanent: true,
    );
    Get.put<PreparednessStateService>(
      PreparednessStateService(),
      permanent: true,
    );
    Get.put<PreparednessRepository>(
      PreparednessRepository(Get.find<PreparednessStateService>()),
      permanent: true,
    );
    Get.put<MlAlertService>(MlAlertService(), permanent: true);

    /// CONTROLLERS
    Get.put<AuthController>(
      AuthController(authRepository: Get.find<AuthRepository>()),
      permanent: true,
    );
    Get.put<ProfileController>(ProfileController(), permanent: true);
    Get.put<ImagePickingController>(ImagePickingController(), permanent: true);
    Get.put<SOSController>(SOSController(), permanent: true);
    Get.put<MlAlertController>(MlAlertController(), permanent: true);
    Get.put<AlertController>(AlertController(), permanent: true);
    Get.put<NotificationController>(NotificationController(), permanent: true);
    Get.put<EmergencyContactController>(
      EmergencyContactController(),
      permanent: true,
    );
    Get.put<PreparednessController>(
      PreparednessController(repository: Get.find<PreparednessRepository>()),
      permanent: true,
    );
  }
}
```

Pattern observations:
- Every registration uses `Get.put<T>(..., permanent: true)`. **`permanent: true` is the default in this file; `lazyPut` is never used here.**
- The file is split into `// SERVICES` then `// CONTROLLERS` sections.
- Constructor injection used where a class has dependencies (`AuthRepository(Get.find<AuthService>())`, `ChatbotService(repository: Get.find<ChatbotRepository>())`, etc.). Order is therefore load-bearing.
- `ConnectivityService`, `OutboxService`, `OutboxController` are **not** registered here — they are registered separately in `main.dart` lines 35–37 (also `permanent: true`) before `runApp` because Hive boxes must open first.
- `ChatController` is **not** in `InitialBindings`. It is created on-demand inside `_ChatViewState`'s field initialiser via plain `Get.put(ChatController(...))` with no `permanent` flag.

### D16. `OutboxService` public interface

`safelink/lib/features/outbox/services/outbox_service.dart`:

```dart
class OutboxService extends GetxService {
  static const String pendingBoxName = 'pending_submissions';
  static const String failedBoxName  = 'failed_submissions';
  static const int maxAttempts = 5;

  int get pendingCount;
  int get failedCount;

  List<PendingSubmission> listPending();
  List<PendingSubmission> listFailed();

  Future<void> enqueue(PendingSubmission item);
  Future<void> remove(String id);
  Future<void> markFailed(PendingSubmission item);
  Future<void> recordAttempt(PendingSubmission item, {String? error});
  Future<void> clearFailed();
  Future<void> requeueFailed(String id);
}
```

Plus the discriminator and payload types:

```dart
class SubmissionKind {
  static const String sos = 'sos';
  static const String disasterReport = 'disaster_report';
}

class PendingSubmission {
  final String id;
  final String kind;
  final Map<String, dynamic> payload;
  final DateTime createdAt;
  final int attempts;
  final String? lastError;

  Map<String, dynamic> toMap();
  factory PendingSubmission.fromMap(Map<dynamic, dynamic> map);
  PendingSubmission copyWith({int? attempts, String? lastError});
}
```

Storage: two `Box<Map>` Hive boxes (`pending_submissions`, `failed_submissions`). No `TypeAdapter` — payload is `Map<String, dynamic>`. Boxes are opened in `main.dart` before service registration; opening them here would not work because `GetxService` registration is sync.

### D17. User/profile model — does it have `province` or `city`?

`safelink/lib/features/profile/models/profile_model.dart` — relevant fields only:

```dart
class ProfileModel {
  final String id;
  final String role;
  final String fullName;
  final String email;
  final String? phone;
  final String? cnic;
  final String? dateOfBirth;
  final String? avatarUrl;
  final String? region;        // ← present
  final String? city;          // ← present
  final double? latitude;
  final double? longitude;
  final String? createdAt;
  final String? updatedAt;
  // ...
}
```

- `city` — **present**, nullable.
- `region` — **present**, nullable. Currently used to mean country/region (e.g., "pakistan"), not province.
- `province` — **NOT present**. No field of that name in `ProfileModel`.

Population: `ProfileModel.fromJson` reads `json['city']`, `json['region']` etc. from Supabase. Whether Supabase rows actually have non-null `city` values is determined by user behaviour during sign-up / profile-edit; that flow is in `features/profile/presentation/screens/edit_profile_view.dart` and is out of scope per the audit boundary, so not verified.

If `province` were to live somewhere, the natural homes are: (a) a new column on the Supabase `profiles` table mirrored into `ProfileModel`, or (b) derived client-side from `city` using a table mirror of the backend's `entity_extractor.CITY_TO_PROVINCE` map.

### D18. `pubspec.yaml`

`dependencies:`

```yaml
flutter:
  sdk: flutter

cupertino_icons: ^1.0.8
get: ^4.7.2
supabase_flutter: ^2.10.3
hive: ^2.2.3
hive_flutter: ^1.1.0
connectivity_plus: ^6.0.0
google_fonts: ^6.3.1
flutter_screenutil: ^5.9.3
font_awesome_flutter: ^10.12.0
shared_preferences: ^2.5.3
flutter_svg: ^2.2.3
image_picker: ^1.2.1
url_launcher: ^6.3.2
http: ^1.6.0
google_maps_flutter: ^2.14.0
geolocator: ^14.0.2
flutter_markdown_plus: ^1.0.7
flutter_animate: ^4.5.2
google_sign_in: ^6.2.1
package_info_plus: ^8.0.0
```

`dev_dependencies:`

```yaml
flutter_test:
  sdk: flutter
flutter_lints: ^6.0.0
```

`uuid` does not appear in the manifest. It is in `pubspec.lock` as `dependency: transitive` only.

---

## E. Frontend — chatbot feature internals

### E19. `chat_models.dart` — relevant model paste

```dart
enum MessageType { user, bot, system }
enum UrgencyLevel { low, medium, critical }

class ChatMessage {
  final String id;
  final String content;
  final MessageType type;
  final DateTime timestamp;
  final bool isEmergency;
  final UrgencyLevel urgencyLevel;
  final List<String> suggestedActions;
  final List<HelplineInfo> helplines;
  final String? intentType;
  final double? confidence;
  final bool isLoading;

  ChatMessage({
    required this.id,
    required this.content,
    required this.type,
    required this.timestamp,
    this.isEmergency = false,
    this.urgencyLevel = UrgencyLevel.low,
    this.suggestedActions = const [],
    this.helplines = const [],
    this.intentType,
    this.confidence,
    this.isLoading = false,
  });

  factory ChatMessage.user(String content) {
    return ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      content: content,
      type: MessageType.user,
      timestamp: DateTime.now(),
    );
  }

  factory ChatMessage.loading() { ... id: 'loading' ... }

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: json['message_id'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
      content: json['response'] ?? json['content'] ?? '',
      type: MessageType.bot,
      timestamp: DateTime.now(),
      isEmergency: json['is_emergency'] ?? false,
      urgencyLevel: _parseUrgencyLevel(json['urgency_level']),
      suggestedActions: List<String>.from(json['suggested_actions'] ?? []),
      helplines: (json['helplines'] as List<dynamic>?)
              ?.map((h) => HelplineInfo.fromJson(h)).toList() ?? [],
      intentType: json['intent_type'],
      confidence: json['confidence']?.toDouble(),
    );
  }
}

class HelplineInfo {
  final String name;
  final String number;
  final String? description;
  final String region;
  final bool available24x7;
  final String? category;

  factory HelplineInfo.fromJson(Map<String, dynamic> json);
  Map<String, dynamic> toJson();
}

class ChatRequest {
  final String message;
  final String? sessionId;
  final String region;
  final Map<String, dynamic>? context;

  ChatRequest({
    required this.message,
    this.sessionId,
    this.region = 'pakistan',
    this.context,
  });

  Map<String, dynamic> toJson() {
    return {
      'message': message,
      'session_id': sessionId,
      'region': region,
      if (context != null) 'context': context,
    };
  }
}

class OfflineData {
  final Map<String, List<HelplineInfo>> helplines;
  final Map<String, String> quickTips;
  final List<String> emergencyKeywords;
  final DateTime lastUpdated;

  factory OfflineData.fromJson(Map<String, dynamic> json) {
    Map<String, List<HelplineInfo>> helplines = {};
    if (json['helplines'] != null) {
      (json['helplines'] as Map<String, dynamic>).forEach((region, data) {
        helplines[region] = (data as List<dynamic>)
            .map((h) => HelplineInfo.fromJson(h)).toList();
      });
    }
    return OfflineData(
      helplines: helplines,
      quickTips: Map<String, String>.from(json['quick_tips'] ?? {}),
      emergencyKeywords: List<String>.from(json['emergency_keywords'] ?? []),
      lastUpdated: DateTime.tryParse(json['last_updated'] ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() { ... }
}
```

Notes from the paste:
- Dart `ChatRequest` has **no `province` or `city` field** — only `message`, `sessionId`, `region`, optional `context`. Matches audit F9: even if the Flutter UI wanted to send province, the model would silently drop it.
- Dart `UrgencyLevel` is `low / medium / critical` — **missing `high`** that the backend's enum has.
- `OfflineData.fromJson` reads `helplines`, `quick_tips`, `emergency_keywords`, `last_updated`. **`guidance_data` and `checksum` from the server response are dropped.**
- `HelplineInfo.fromJson` ignores any field the backend doesn't currently send (e.g., `verified_at`).

### E20. `ChatController` registration

`safelink/lib/features/chatbot/presentation/screens/chat_view.dart:21–24`:

```dart
final ChatController _chatController = Get.put(
  ChatController(chatService: Get.find<ChatbotService>()),
);
```

- Registered as a **field initialiser** of the `_ChatViewState` class.
- No `permanent: true` flag — diverges from the convention in `InitialBindings`.
- Each time `ChatView` is mounted (including bottom-nav switches that recreate the State), `Get.put` runs again. By default `Get.put` replaces the existing instance, so the old controller and its messages are lost.
- Not present in `InitialBindings`.

### E21. Chatbot widget files & import status

Files in `safelink/lib/features/chatbot/presentation/widgets/`:

| File | Imported by |
|---|---|
| `chat_bubble.dart` | `chat_view.dart:10` ✅ used |
| `quick_action.dart` | `chat_view.dart:11` ✅ used |
| `helpline_button.dart` | nothing — `chat_bubble.dart` instead has its own private `_buildHelplineButton(...)` method (lines 286–375) that duplicates the styling. ❌ **ORPHAN** |
| `offline_banner.dart` | nothing. ❌ **ORPHAN** |
| `s_o_s_button.dart` | nothing. ❌ **ORPHAN** |

**Three orphan widgets**, not two. The previous audit's F15 listed only `offline_banner.dart` and `s_o_s_button.dart`; `helpline_button.dart` is also unused.

### E22. Chat screen UI shape (one-paragraph description)

The screen is a `Scaffold` containing a vertical `Column` inside `SafeArea`:

1. **Header** — `GradientHeader` with the app's primary gradient. Inside: a circular SVG assistant icon (with two-layer drop shadow), the title text "AI Assistant", a small status line that shows a green or red dot plus the literal word "Online" or "Offline" (read from `_chatController.isOffline.value` via `Obx`), and on the far right a delete icon (visible only when there are messages) that opens a confirm-clear-chat dialog.
2. **Body** — an `Expanded` region with two states: when `messages.isEmpty`, it shows a "Quick Help" greeting screen with four `QuickAction` tiles (First Aid, Earthquake Safety, Flood Safety, Medical Help) arranged in a 2×2 grid, then a blue-tinted info card that says "Assalam-o-Alaikum! 👋 I'm your SafeLink Safety Assistant…" When messages exist, it shows a `ListView.builder` of `ChatBubble` widgets scrolled by a `ScrollController`. The post-frame `_scrollToBottom()` callback is registered inside the `Obx` builder (audit F14).
3. **Input row** — a `Row` with a rounded-rectangle `TextField` (placeholder "Type your message..."), and to its right a circular send button with the primary gradient, an SVG paper-plane icon, and an `InkWell` ripple. Submission triggers `_chatController.sendMessage()`.

Not visible anywhere on the screen: an offline banner, a reconnect affordance, sources/citations, conversation persistence indicator, suggested-question chips outside of bot bubbles, message-action long-press menu.

### E23. Message styling (brief)

- **User bubbles:** right-aligned, `AppTheme.primaryGradient` background, white text, all-rounded corners. Left margin of 60w to keep them away from the screen edge.
- **Bot bubbles:** left-aligned, `theme.cardColor` background (light/dark adaptive), default text colour, all-rounded corners. Right margin of 60w.
- **Emergency / critical bubbles** (when `isEmergency || urgencyLevel == critical`): a small red "EMERGENCY" pill with a warning icon is rendered above the bubble. The bubble itself uses `AppTheme.red.withValues(alpha: 0.1)` background and a red 30%-alpha border.
- **Loading bubble:** left-aligned, theme `cardColor`, contains a `CircularProgressIndicator` (strokeWidth 1) and the literal text "Typing...". Replaces a placeholder message with `id: 'loading'` and `isLoading: true`.
- **System messages:** centre-aligned pill in the primary colour at 10% alpha, italic text in primary colour. Used only for the "✅ Back online!" message produced by `tryReconnect` (which is itself never invoked from the UI).
- **Markdown rendering:** `MarkdownBody` from `flutter_markdown_plus`. Bold, lists, links supported. Link taps call `launchUrl(uri)` with no scheme allowlist (audit F12).
- **Helpline cards inside bubbles:** green-tinted rounded rectangles with a phone icon, name, number, optional `24/7` badge, optional one-line description. Taps fire `tel:` URI via `url_launcher`.
- **Suggested-action chips:** below the bubble content as a `Wrap` of pill-shaped containers in primary colour at 10% alpha with a 30%-alpha border. Tapping a chip resends the chip text as a new message.
- **Bubble metadata:** below each bubble — relative timestamp (e.g., "5m ago") and, for bot messages, thumbs-up / thumbs-down feedback icons.

Padding is 15.r inside bubbles; bubbles are separated by 10.h vertical margin; horizontal gutter to the opposing edge is 60.w. Border radius is `15.r` (uniform; not the asymmetric corners common in modern chat designs).

---

## F. Audit findings — confirm / not reproducible / different

### Frontend

| ID | Description | Status | Note |
|---|---|---|---|
| F1 | Hardcoded `baseUrl` for chatbot | **CONFIRMED** | `chatbot_remote_service.dart:6` |
| F2 | Health URL uses `..` traversal | **CONFIRMED** | `chatbot_remote_service.dart:95` |
| F3 | `OfflineBanner` not rendered | **CONFIRMED** | grep across `lib/`: imported nowhere |
| F4 | Sticky `_isOffline` flag | **CONFIRMED** | `chatbot_repository.dart:48`; only reset inside `syncOfflineData` and `tryReconnect`, neither called automatically while online |
| F5 | Misleading "Feedback saved locally" | **CONFIRMED** | `chat_bubble.dart:44–46`; nothing is saved locally |
| F6 | `_repository.initialize()` not awaited | **CONFIRMED** | `chatbot_service.dart:9` |
| F7 | `ChatController` recreated on nav | **CONFIRMED** | `chat_view.dart:21–24` field initialiser, no `permanent` |
| F8 | `guidance_data` dropped client-side | **CONFIRMED** | `chat_models.dart:160–177` |
| F9 | Province/city never sent | **CONFIRMED** | grep over `features/chatbot`: zero hits for `province`/`city`. Also: Dart `ChatRequest` has no `province`/`city` field, so adding them needs a model change too. |
| F10 | No checksum compare | **CONFIRMED** | `chatbot_repository.dart:59–69` |
| F11 | Offline router only earthquake/flood | **CONFIRMED** | `chatbot_offline_response_service.dart:115–125` |
| F12 | `onTapLink` no scheme allowlist | **CONFIRMED** | `chat_bubble.dart:188–195` |
| F13 | Timestamp-based message IDs | **CONFIRMED** | `chat_models.dart:34, 54`; `chatbot_offline_response_service.dart:50`; loading bubble uses literal `'loading'` |
| F14 | `addPostFrameCallback` inside `Obx` | **CONFIRMED** | `chat_view.dart:294–296` |
| F15 | Orphan widgets (2) | **DIFFERENT** | There are **3** orphan widget files, not 2: `offline_banner.dart`, `s_o_s_button.dart`, **and `helpline_button.dart`**. The third is duplicated by a private `_buildHelplineButton` method in `chat_bubble.dart`. |
| F16 | Duplicate `trim().isEmpty` check | **CONFIRMED** | `chat_view.dart:49` (`text.isNotEmpty`) and `chat_controller.dart:30` (`text.trim().isEmpty`) |

### Backend

| ID | Description | Status | Note |
|---|---|---|---|
| B1 | CORS `*` + `allow_credentials=True` | **CONFIRMED** | `main.py:78–83`; CORS spec violation when origin is `*` |
| B2 | Feedback log on ephemeral FS | **CONFIRMED** | `routers/chat_router.py:28–30, 84–89` |
| B3 | No auth, no rate limit | **CONFIRMED** | `slowapi` not installed; no `Depends(...)` on routes; `RATE_LIMIT_*` settings exist but are never read |
| B4 | `\bhelp me\b` over-fires EMERGENCY | **CONFIRMED** | `nlp/intent_classifier.py:41` |
| B5 | `session_id` accepted, never persisted | **CONFIRMED** | No session store class, no Redis usage; `session_id` is read only inside `process_message`'s prologue and not stored |
| B6 | PII regex misses landlines & unhyphenated CNICs | **CONFIRMED** | `nlp/preprocessor.py:144` — phone_pk regex requires `0?3\d{2}` (mobile only); CNIC regex `\d{5}[-\s]?\d{7}[-\s]?\d{1}` requires separators |
| B7 | Small training set | **CONFIRMED** | `nlp/intent_classifier.py:118–271`, ~120 samples across 14 classes |
| B8 | `/offline-data` rebuilt every request | **CONFIRMED** | `routers/chat_router.py:140–209`, no memoisation |
| B9 | `datetime.utcnow()` deprecated in 3.12+ | **CONFIRMED** | `main.py:110, 142`; `models/schemas.py:128, 167`; `routers/chat_router.py:75` |
| B10 | First-aid handler uses hardcoded `0.20` floor | **CONFIRMED** | `services/chatbot_service.py:577` |
| B11 | `general` entries leak into filtered results | **CONFIRMED** | `nlp/knowledge_retriever.py:154–165`; explicit `if entry.disaster_type != 'general': continue` clause makes general universally retrievable. Behaviour is intentional but not documented in the function docstring. |
| B12 | Relative feedback path | **CONFIRMED** | `routers/chat_router.py:28–30` joins `__file__` with `..` — works as long as cwd doesn't matter to imports, but is brittle |

### Totals

- **Confirmed:** 27
- **Different:** 1 (F15)
- **Not reproducible:** 0

---

## G. Anything else worth flagging for planning

- **Dart `ChatRequest` has fewer fields than backend `ChatRequest`.** Dart side has only `message`, `sessionId`, `region`, optional `context`. Backend has `province`, `city`, `language`, `location`, `offline_context`, `user_id` in addition. Even if the UI started passing province/city, the Dart model and remote service body would silently drop them — this needs to be fixed in tandem with audit F9, not just at the UI layer.
- **Dart `UrgencyLevel` enum is missing `HIGH`.** Backend has `LOW / MEDIUM / HIGH / CRITICAL`; Dart has `low / medium / critical`. `_parseUrgencyLevel` in `chat_models.dart:72–81` falls through to `low` for any unknown value, including `"high"`. Backend handlers like `_handle_report_incident` set `urgency_level=HIGH`, which the client renders as `low`.
- **`ChatMessage.fromJson` reads `json['intent_type']`, but the backend response has `intent: IntentResult` (an object), not a flat `intent_type` string.** The field as written is always null on real responses; the Dart model has effectively never seen a populated intent type from the wire.
- **The chatbot's offline session ID and the backend's `session_id` are unrelated.** Dart side persists `session_${epoch_ms}` in SharedPreferences; backend doesn't store sessions at all. Clearing chat regenerates the local ID with no server-side effect.
- **Backend `_handle_emergency` (`services/chatbot_service.py:217`) trims `specific_guidance` to 600 chars** explicitly so the message stays scannable in panic. Worth knowing — any LLM-generated emergency content needs to honour this constraint.
- **The backend's `_check_emergency` (`services/chatbot_service.py:193`) has three independent triggers**: hard-coded phrase list, set-overlap of ≥2 emergency keywords, and `urgency_score >= 0.6` from the preprocessor. The phrase list and the keyword list are both populated; the `\bhelp me\b` regex (B4) is in a *fourth* place (the rule-based intent classifier, line 41). So fixing B4 alone does not eliminate the over-fire — the keyword set in `EMERGENCY_KEYWORDS` env var still includes the bare token `help`.
- **Trained intent classifier is persisted at `/tmp/safelink_chatbot/intent_classifier_lr_v3.joblib`.** The `v3` suffix implies prior schema changes; expect to bump the filename when the training set or pipeline changes again.
- **`OfflineDataResponse` (`models/schemas.py:138–150`) ships `guidance_data` as `List[GuidanceContent]`,** which has step-list fields (`before_steps`, `during_steps`, `after_steps`). The actual `/offline-data` route (`chat_router.py:148–162`) populates `guidance_data` with empty step lists and only a 240-char `summary` — so even if the Flutter side were to consume `guidance_data`, the steps would be empty.
- **`ChatbotService.sendMessage` constructor in Dart** (`chatbot_service.dart:7–10`) immediately calls `_repository.initialize()` without awaiting, **and the constructor itself runs at `InitialBindings` registration time** because it's a `Get.put` with eager construction. The race window for F6 starts at app boot, not at chat-screen open.
- **`flutter_markdown_plus` is the markdown renderer.** Worth noting because some markdown packages strip raw HTML differently and `chat_bubble.dart`'s lack of a scheme allowlist (F12) is the only client-side defence.
- **`google_sign_in: ^6.2.1` is the version pin.** The Google Sign-In v7+ has breaking API changes; the chatbot itself doesn't touch sign-in but anything that adds OAuth-based chatbot endpoints needs to be aware.
- **`SafetyStep` and `GuidanceContent` Pydantic models exist but are barely used.** `SafetyStep.is_critical` and `GuidanceContent.warnings`/`helpful_links` are wire fields that the current `/offline-data` route never populates. If a future pipeline relies on them, the route is the only place that constructs them.
- **Roman Urdu keywords appear in three separate places:** `chatbot_offline_response_service.dart:79–81, 117–118` (Flutter offline router); `nlp/intent_classifier.py:49, 57, 247–248, 263` (backend intent rules + training); `nlp/preprocessor.py:127–137` (spell-corrections like `kpk`, `ajk`, `ndma`). They're not centralised — refactors that touch any of these layers must keep parity.
- **`IntentTypes.SAFETY_ADVICE` is the most-used intent in the LR training data,** with ~22 samples versus 5–7 for most others. The LR's class balance is enforced via `class_weight='balanced'`, but rule patterns dominate in practice for the high-confidence intents (greetings, gratitude, emergency, helpline_query, first_aid).
- **`_handle_safety_advice` returns `urgency_level=MEDIUM` and `_handle_first_aid` returns `urgency_level=MEDIUM`** — but the Dart enum doesn't have `medium`-styled rendering distinct from `low` (only `critical` gets the red border treatment). Medium-urgency responses look identical to low-urgency ones in the UI.
- **The chatbot has no per-conversation rate limit,** even client-side. A user holding the send button or pasting a long prompt repeatedly will fire as many requests as their network can handle.
- **No structured logging anywhere in the chatbot pipeline.** The middleware logs `method path status time`, but `process_message`, the LLM-less intent path, and emergency dispatch all use `logger.info(f"…")` plain-text strings. There is no `request_id`, no `session_id_hash`, no `intent` field in logs. Observability is effectively absent.
