"""
API-key authentication + slowapi rate limiter setup.

## Auth contract (locked Phase 1 decision)

- **DEBUG=True** mode: `require_api_key` accepts any value (including missing
  header). This is the local-dev / test posture so curl + integration tests
  can hit the API without juggling secrets.
- **DEBUG=False** mode: `require_api_key` requires the request to carry
  `X-API-Key: <settings.CHATBOT_API_KEY>` exactly. Anything else returns 401.
  Startup also asserts that `CHATBOT_API_KEY` is non-empty in this mode (see
  main.py); a deploy with `DEBUG=False` and no key will refuse to start.

Introspection routes (`/chat/intents`, `/chat/disasters`, `/`, `/health`,
`/api/v1/health`, `/ready`) are intentionally NOT wrapped with this dependency
so basic liveness probing works without credentials.
"""
from fastapi import Header, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import get_settings


# ─── Rate limiter ─────────────────────────────────────────────────────────────
# Per-IP limiter. Routes attach decorators (@limiter.limit(...)) per-endpoint
# with their own quotas so chat and feedback can have different ceilings.
limiter = Limiter(key_func=get_remote_address)


# ─── API-key dependency ───────────────────────────────────────────────────────
async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    FastAPI Depends() guard. Raises 401 if the request fails the auth contract
    above. In DEBUG mode this is a no-op.
    """
    settings = get_settings()
    if settings.DEBUG:
        return  # dev-mode bypass (locked Phase 1 decision)

    expected = settings.CHATBOT_API_KEY
    if not expected:
        # Production with no key configured — refuse rather than allow open access.
        # main.py's startup check should have prevented this, but defense-in-depth.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth misconfigured",
        )

    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
