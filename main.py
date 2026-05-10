"""
SafeLink Safety Chatbot — FastAPI entrypoint.

Pakistan-first disaster relief chatbot.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
from datetime import datetime, timezone

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import get_settings
from routers import chat_router
from models import HealthCheckResponse
from services.auth import limiter

# ─── Logging ──────────────────────────────────────────────────────────────────
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Startup auth check ───────────────────────────────────────────────────────
def _assert_auth_configured() -> None:
    """
    Refuse to boot a non-DEBUG instance without an API key. Prevents accidentally
    deploying an unauthenticated chatbot to production. DEBUG mode bypasses
    by design (see services/auth.py docstring).
    """
    if settings.DEBUG:
        return
    if not (settings.CHATBOT_API_KEY or "").strip():
        raise RuntimeError(
            "CHATBOT_API_KEY is empty and DEBUG is False. Refusing to start an "
            "unauthenticated production chatbot. Set CHATBOT_API_KEY in env "
            "(or DEBUG=true for local dev)."
        )


def _assert_llm_configured_if_enabled() -> None:
    """
    When USE_LLM=true, at least one provider key must be configured. We
    fail fast at startup rather than at first-request time so a bad deploy
    is visible in the build logs.
    """
    if not settings.USE_LLM:
        return
    has_gemini = bool((settings.GEMINI_API_KEY or "").strip())
    has_groq = bool((settings.GROQ_API_KEY or "").strip())
    if not (has_gemini or has_groq):
        raise RuntimeError(
            "USE_LLM=true but neither GEMINI_API_KEY nor GROQ_API_KEY is set. "
            "Either set at least one provider key, or set USE_LLM=false to "
            "run the legacy pipeline."
        )


# ─── Lifespan: warm up the chatbot service so first request is fast ───────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Default region: {settings.DEFAULT_REGION}")
    logger.info(f"Embeddings enabled: {settings.USE_EMBEDDINGS}")
    logger.info(f"Model cache dir: {settings.MODEL_CACHE_DIR}")
    logger.info(f"DEBUG mode: {settings.DEBUG}")

    _assert_auth_configured()
    _assert_llm_configured_if_enabled()

    try:
        from services import get_chatbot_service
        from services.session_store import get_session_store

        get_chatbot_service()  # Triggers eager init of NLP pipeline
        app.state.chatbot_ready = True
        logger.info("Chatbot service initialised successfully")

        # Phase 3: kick off the periodic session sweeper so expired sessions
        # are evicted on the SESSION_SWEEP_INTERVAL_SECONDS cadence.
        store = get_session_store()
        store.start_sweeper()
        app.state.session_store = store
        logger.info(
            "Session sweeper started (TTL=%dm, max_active=%d, USE_LLM=%s)",
            settings.SESSION_TTL_MINUTES,
            settings.SESSION_MAX_ACTIVE,
            settings.USE_LLM,
        )
    except Exception as e:
        app.state.chatbot_ready = False
        logger.error(f"Failed to initialise chatbot service: {e}", exc_info=True)

    yield

    # Graceful shutdown of the session sweeper.
    try:
        store = getattr(app.state, "session_store", None)
        if store is not None:
            await store.stop_sweeper()
    except Exception as e:
        logger.warning("Sweeper shutdown error: %s", e)
    logger.info("Shutting down SafeLink Chatbot Server")


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="""
## SafeLink Safety Chatbot API — Pakistan

A disaster relief chatbot providing:
- **Disaster Safety Guidance** — Earthquake, Flood, Heatwave, Cyclone, Fire, Gas Leak, Building Collapse
- **Pakistan Emergency Helplines** — Federal & provincial (1122, 115, 15, 16, NDMA, PDMAs)
- **First Aid Information** — Bleeding, CPR, burns, snake bite, electric shock, heat stroke, fractures, choking, drowning
- **Evacuation & Shelter Guidance**
- **Mental Health Support** — Post-disaster coping, referrals (Rozan, Umang)
- **Donation & Volunteering** — Trusted Pakistani relief organisations
- **Offline Support** — Cacheable bundle for offline-first mobile clients

### Safety First
- Verified, human-authored guidance
- Clear emergency escalation paths
- Appropriate medical disclaimers
- Never provides medical diagnoses or legal advice
""",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Rate limiting ────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ─── CORS ─────────────────────────────────────────────────────────────────────
# Browsers reject `*` + credentials. cors_allow_credentials returns False
# whenever origins resolve to ["*"]; True otherwise.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request logging middleware ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} — "
        f"status={response.status_code} time={process_time:.3f}s"
    )
    response.headers["X-Process-Time"] = f"{process_time:.3f}"
    return response


# ─── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. For emergencies, call 115 or 1122.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(chat_router, prefix=settings.API_PREFIX)


# ─── Root + Health ────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "country": "Pakistan",
        "docs": "/docs",
        "api_base": settings.API_PREFIX,
    }


def _build_health_response() -> HealthCheckResponse:
    is_ready = getattr(app.state, "chatbot_ready", False)
    return HealthCheckResponse(
        status="healthy" if is_ready else "starting",
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc),
        services={
            "api": "healthy",
            "chatbot": "healthy" if is_ready else "starting",
        },
    )


@app.get("/health", response_model=HealthCheckResponse, tags=["Health"])
async def health_check(request: Request):
    """
    Lightweight health check — does NOT instantiate the chatbot service.
    Used by Railway's healthcheck (railway.json points here). For a deeper
    readiness probe, use /ready.
    """
    return _build_health_response()


@app.get(
    f"{settings.API_PREFIX}/health",
    response_model=HealthCheckResponse,
    tags=["Health"],
)
async def health_check_v1(request: Request):
    """
    Mirror of /health under the API prefix. Exists so the Flutter client
    (which already prefixes every chatbot URL with /api/v1) can probe health
    without path-traversal hacks.
    """
    return _build_health_response()


@app.get("/ready", tags=["Health"])
async def ready_check():
    """Readiness probe — confirms NLP pipeline is loaded."""
    try:
        from services import get_chatbot_service

        get_chatbot_service()
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "error": str(e)},
        )


if __name__ == "__main__":
    # Local dev only — Railway uses the Procfile / nixpacks startCommand.
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
