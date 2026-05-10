"""API Router for chat endpoints."""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from config import IntentTypes, DisasterTypes, get_settings
from models import (
    ChatRequest,
    ChatResponse,
    ChatStreamChunk,
    ErrorResponse,
    FeedbackRequest,
    OfflineDataResponse,
    SourceCitation,
)
from services import get_chatbot_service
from services.auth import limiter, require_api_key
from services.feedback_log import (
    append_feedback,
    feedback_record,
    resolve_feedback_log_path,
)
from services.offline_bundle import get_offline_bundle_builder

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/chat", tags=["Chat"])

# Resolved once at import (env-driven). main.py's startup check guarantees
# the parent directory exists before the first write.
FEEDBACK_LOG = resolve_feedback_log_path(settings)


# ─── /chat/message ────────────────────────────────────────────────────────────
@router.post(
    "/message",
    response_model=ChatResponse,
    summary="Send a message to the safety chatbot",
    responses={
        200: {"description": "Successful response with safety guidance"},
        400: {"description": "Invalid request", "model": ErrorResponse},
        401: {"description": "Missing or invalid API key"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(lambda: f"{settings.RATE_LIMIT_CHAT_PER_MIN}/minute")
async def send_message(request: Request, payload: ChatRequest):
    start_time = time.time()
    try:
        chatbot = get_chatbot_service()
        response = await chatbot.process_message(payload)
        elapsed = time.time() - start_time
        logger.info(
            f"Message processed in {elapsed:.3f}s — intent={response.intent.intent}"
        )
        return response
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred. For emergencies, call 1122 or 115.",
        )


# ─── /chat/stream (SSE) ───────────────────────────────────────────────────────
# Locked O7 — POST despite SSE convention, so the body schema matches /message.
@router.post(
    "/stream",
    summary="Stream a chat response as Server-Sent Events",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(lambda: f"{settings.RATE_LIMIT_CHAT_PER_MIN}/minute")
async def stream_message(request: Request, payload: ChatRequest):
    """
    SSE stream of `ChatStreamChunk` JSON payloads. Final chunk has
    ``done: true`` and carries the metadata (sources, helplines, etc.).

    When ``USE_LLM=false`` the endpoint still works — it produces the
    legacy template response in two chunks (full delta + done). Clients
    should treat both modes uniformly.
    """
    chatbot = get_chatbot_service()

    async def event_generator():
        try:
            response = await chatbot.process_message(payload)
        except Exception as e:
            logger.error(f"Streaming /chat/message failed: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": ChatStreamChunk(
                    message_id="error",
                    done=True,
                    error="An error occurred. For emergencies, call 1122 or 115.",
                ).model_dump_json(),
            }
            return

        # v1 of streaming: yield the full text as one delta then a done
        # marker. The LLMService.generate_stream() helper exists for
        # provider-native streaming; wiring it here is a v1.1 task once
        # tool-call interactions across providers stabilise.
        text = response.response or ""
        chunk_size = 80
        for i in range(0, max(len(text), 1), chunk_size):
            piece = text[i : i + chunk_size]
            yield {
                "event": "delta",
                "data": ChatStreamChunk(
                    message_id=response.message_id,
                    delta=piece,
                ).model_dump_json(),
            }

        yield {
            "event": "done",
            "data": ChatStreamChunk(
                message_id=response.message_id,
                done=True,
                sources=response.sources,
                helplines=response.helplines,
                suggested_actions=response.suggested_actions,
                used_llm=response.used_llm,
                provider_used="llm" if response.used_llm else "legacy",
            ).model_dump_json(),
        }

    return EventSourceResponse(event_generator())


# ─── /chat/feedback ───────────────────────────────────────────────────────────
@router.post(
    "/feedback",
    summary="Submit feedback on a response",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(lambda: f"{settings.RATE_LIMIT_FEEDBACK_PER_MIN}/minute")
async def submit_feedback(request: Request, feedback: FeedbackRequest):
    """
    Persists feedback as JSONL (append-only). The path comes from
    settings.FEEDBACK_LOG_PATH; mount a volume there for durability.
    """
    try:
        record = feedback_record(
            message_id=feedback.message_id,
            session_id=feedback.session_id,
            rating=feedback.rating,
            helpful=feedback.helpful,
            comment=feedback.comment,
            feedback_text=feedback.feedback_text,
        )
        append_feedback(record, FEEDBACK_LOG)

        logger.info(
            f"Feedback received — message={feedback.message_id} helpful={feedback.helpful}"
        )
        return {"status": "success", "message": "Thank you for your feedback!"}
    except Exception as e:
        logger.error(f"Error storing feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to store feedback")


# ─── /chat/helplines/{region} ─────────────────────────────────────────────────
@router.get(
    "/helplines/{region}",
    summary="Get helplines for a region",
    dependencies=[Depends(require_api_key)],
)
async def get_helplines(
    region: str, category: Optional[str] = None, province: Optional[str] = None
):
    try:
        chatbot = get_chatbot_service()
        normalized = chatbot._normalize_region(region)

        categories = [category] if category else None
        helplines = chatbot._get_helplines(
            normalized, province=province, categories=categories, limit=20
        )

        if not helplines:
            raise HTTPException(
                status_code=404, detail=f"No helplines found for region: {region}"
            )

        return {
            "region": normalized,
            "province": province,
            "helplines": [h.model_dump() for h in helplines],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting helplines: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve helplines")


# ─── /chat/offline-data ───────────────────────────────────────────────────────
@router.get(
    "/offline-data",
    response_model=OfflineDataResponse,
    summary="Get offline data package",
    dependencies=[Depends(require_api_key)],
)
async def get_offline_data(region: str = "pakistan"):
    """
    Cacheable offline bundle. Phase 3: rebuilt only on KB-version change or
    cache TTL expiry; populated `guidance_data` step lists from v2 KB
    (audit B8 + F8 backend side).
    """
    try:
        chatbot = get_chatbot_service()
        builder = get_offline_bundle_builder()
        return builder.build(chatbot, region=region)
    except Exception as e:
        logger.error(f"Error generating offline data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate offline data")


# ─── /chat/quick-tip/{disaster_type} ──────────────────────────────────────────
@router.get(
    "/quick-tip/{disaster_type}",
    summary="Get quick safety tip",
    dependencies=[Depends(require_api_key)],
)
async def get_quick_tip(disaster_type: str):
    try:
        chatbot = get_chatbot_service()
        tips = chatbot.templates.get("quick_tips", {}) or {}
        tip = tips.get(disaster_type.lower())
        if not tip:
            raise HTTPException(
                status_code=404,
                detail=f"No quick tip for '{disaster_type}'. Available: {list(tips.keys())}",
            )
        return {"disaster_type": disaster_type, "tip": tip}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quick tip: {e}")
        raise HTTPException(status_code=500, detail="Failed to get quick tip")


# ─── /chat/intents (introspection) ────────────────────────────────────────────
@router.get("/intents", summary="List supported intents")
async def list_intents():
    return {"intents": IntentTypes.all()}


# ─── /chat/disasters (introspection) ──────────────────────────────────────────
@router.get("/disasters", summary="List supported disaster types")
async def list_disasters():
    return {"disasters": DisasterTypes.all()}
