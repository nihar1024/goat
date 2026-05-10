"""Unit tests for goatobs.context — contextvars + bind_user_context."""
import pytest

from goatobs.context import bind_user_context, get_user_context


def test_no_context_by_default():
    """Outside a bind_user_context block, get_user_context returns empty dict."""
    assert get_user_context() == {}


def test_bind_sets_context_inside_block():
    """Inside the context manager, bound fields are readable."""
    with bind_user_context(user_id="u1", email="a@b.com", realm="p4b"):
        ctx = get_user_context()
        assert ctx == {"user_id": "u1", "email": "a@b.com", "realm": "p4b"}


def test_bind_clears_context_on_exit():
    """After the context manager exits, the previous (empty) context is restored."""
    with bind_user_context(user_id="u1", email="a@b.com", realm="p4b"):
        pass
    assert get_user_context() == {}


def test_nested_bind_overrides_then_restores():
    """Nested binds shadow the outer context, restored on inner exit."""
    with bind_user_context(user_id="u1", email="a@b.com", realm="p4b"):
        with bind_user_context(user_id="u2", email="c@d.com", realm="p4b"):
            assert get_user_context()["user_id"] == "u2"
        assert get_user_context()["user_id"] == "u1"


def test_bind_accepts_extra_kwargs():
    """Extra kwargs (e.g. roles) are passed through into the context."""
    with bind_user_context(user_id="u1", email="a@b.com", realm="p4b", roles=["admin"]):
        ctx = get_user_context()
        assert ctx["roles"] == ["admin"]
