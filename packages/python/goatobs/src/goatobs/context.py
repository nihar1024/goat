"""User-context propagation via contextvars.

Set once per request by the per-service auth middleware (after JWT
verification), read transparently by the structlog processor and the
OTel span attribute processor. Endpoints don't need to thread user
data through every log call.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

# Single contextvar holding the whole user dict — atomic swap, no
# partial reads. `default={}` so reading outside a request is safe.
_user_ctx: ContextVar[dict[str, Any]] = ContextVar("user_ctx", default={})


def get_user_context() -> dict[str, Any]:
    """Return the current user context dict, or {} if no context is bound."""
    return _user_ctx.get()


@contextmanager
def bind_user_context(
    *,
    user_id: str,
    email: str,
    realm: str,
    **extra: Any,
) -> Iterator[None]:
    """Bind user context for the duration of the block.

    Used by the per-service auth middleware after the JWT has been
    verified — extracts user_id/email/realm from the validated token
    and binds them so the rest of the request handles them automatically.

    The extra kwargs (e.g. `roles=["admin"]`) are passed through into
    the context dict for downstream consumption.
    """
    new_ctx = {"user_id": user_id, "email": email, "realm": realm, **extra}
    token = _user_ctx.set(new_ctx)
    try:
        yield
    finally:
        _user_ctx.reset(token)
