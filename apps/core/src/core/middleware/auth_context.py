"""Per-service auth context middleware.

Runs after CORS, before route handlers. For every incoming request:

  * Tries to extract a Bearer token from the Authorization header.
  * If present, calls the existing core.deps.auth.decode_token —
    which delegates to goatlib.auth.KeycloakAuth — to verify and
    decode the JWT.
  * On success, calls bind_user_context for the duration of the
    request handling. Logs (via structlog) and OTel spans started
    inside the request inherit user_id / email / realm automatically.

For unauthenticated requests (no header, malformed token, expired
token), the middleware just doesn't bind context — it doesn't reject
the request. Per-endpoint Depends(auth) keeps the existing 401 path.
"""
from typing import Any, Callable
from urllib.parse import urlparse

from fastapi import Request, Response
from goatlib.auth import JOSEError

from core.deps.auth import decode_token
from goatobs import bind_user_context


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    return auth.split(" ", 1)[1].strip() or None


def _extract_user_fields(payload: dict[str, Any]) -> dict[str, str] | None:
    """Pull the three fields we bind. Returns None if user_id is absent."""
    user_id = payload.get("sub")
    if not user_id:
        return None
    email = payload.get("email", "")
    # Keycloak's `iss` is `<base>/realms/<realm>`; pull the last path segment.
    iss = payload.get("iss", "")
    realm = ""
    if iss:
        parts = urlparse(iss).path.rstrip("/").split("/")
        if "realms" in parts:
            i = parts.index("realms")
            if i + 1 < len(parts):
                realm = parts[i + 1]
    return {"user_id": user_id, "email": email, "realm": realm}


async def auth_context_middleware(
    request: Request,
    call_next: Callable[[Request], Any],
) -> Response:
    token = _bearer_token(request)
    if not token:
        return await call_next(request)

    try:
        payload = decode_token(token)
    except JOSEError:
        # Verification failed — let the per-endpoint auth dep handle the 401.
        return await call_next(request)

    fields = _extract_user_fields(payload)
    if not fields:
        return await call_next(request)

    with bind_user_context(**fields):
        return await call_next(request)
