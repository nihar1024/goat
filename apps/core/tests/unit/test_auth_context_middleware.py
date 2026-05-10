"""Unit tests for auth_context_middleware.

We test that:
  - Requests carrying a valid JWT bind user context (user_id, email, realm).
  - Requests with no Authorization header don't bind anything.
  - Requests with a malformed/expired JWT don't bind anything (and don't 500).
"""
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient

from core.middleware.auth_context import auth_context_middleware
from goatobs.context import get_user_context


def _make_app(captured: list[dict[str, Any]]) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(auth_context_middleware)

    @app.get("/echo")
    async def _echo(_request: Request):
        captured.append(get_user_context())
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_no_token_no_context():
    captured: list[dict[str, Any]] = []
    app = _make_app(captured)
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/echo")
    assert r.status_code == 200
    assert captured == [{}]


@pytest.mark.asyncio
async def test_valid_token_binds_context():
    captured: list[dict[str, Any]] = []
    app = _make_app(captured)

    fake_payload = {
        "sub": "user-id-123",
        "email": "alice@example.com",
        "iss": "https://kc/realms/p4b",
    }
    with patch("core.middleware.auth_context.decode_token", return_value=fake_payload):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            r = await ac.get("/echo", headers={"Authorization": "Bearer fake.jwt.token"})

    assert r.status_code == 200
    assert captured[0]["user_id"] == "user-id-123"
    assert captured[0]["email"] == "alice@example.com"
    assert captured[0]["realm"] == "p4b"


@pytest.mark.asyncio
async def test_invalid_token_no_context_no_500():
    """Token verification failure should not 500 — it just means no context."""
    captured: list[dict[str, Any]] = []
    app = _make_app(captured)

    from goatlib.auth import JOSEError

    with patch(
        "core.middleware.auth_context.decode_token",
        side_effect=JOSEError("expired"),
    ):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            r = await ac.get("/echo", headers={"Authorization": "Bearer bad.jwt"})

    assert r.status_code == 200
    assert captured == [{}]
