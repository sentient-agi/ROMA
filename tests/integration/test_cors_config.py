"""CORS configuration tests for the ROMA-DSPy FastAPI app.

Regression coverage for the misconfiguration where create_app() emitted
`Access-Control-Allow-Origin: *` together with
`Access-Control-Allow-Credentials: true`. Browsers reject that combination
per the CORS specification, so cross-origin callers with cookies or an
Authorization header could never reach the API.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_main():
    """Reload roma_dspy.api.main so module-level env reads happen inside the test."""

    def _reload():
        import roma_dspy.api.main as main_module

        return importlib.reload(main_module)

    return _reload


def _find_cors_middleware(app):
    from fastapi.middleware.cors import CORSMiddleware

    for entry in app.user_middleware:
        if entry.cls is CORSMiddleware:
            return entry
    raise AssertionError("CORSMiddleware was not registered on the FastAPI app")


def test_default_wildcard_disables_credentials(monkeypatch, reload_main):
    """Without ALLOWED_ORIGINS, the wildcard origin must turn credentials off.

    `allow_origins=['*']` plus `allow_credentials=True` is rejected by every
    modern browser; the dev default must therefore drop credentials so the
    middleware emits a spec-valid response.
    """
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    main_module = reload_main()
    app = main_module.create_app(enable_rate_limit=False)

    entry = _find_cors_middleware(app)
    assert entry.kwargs["allow_origins"] == ["*"]
    assert entry.kwargs["allow_credentials"] is False


def test_explicit_origin_enables_credentials(monkeypatch, reload_main):
    """An explicit ALLOWED_ORIGINS list keeps credentialed CORS on."""
    monkeypatch.setenv(
        "ALLOWED_ORIGINS", "https://app.example.com, https://admin.example.com"
    )
    main_module = reload_main()
    app = main_module.create_app(enable_rate_limit=False)

    entry = _find_cors_middleware(app)
    assert entry.kwargs["allow_origins"] == [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    assert entry.kwargs["allow_credentials"] is True


def test_blank_allowed_origins_falls_back_to_wildcard(monkeypatch, reload_main):
    """An empty / whitespace-only ALLOWED_ORIGINS behaves like the unset case."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "   ,   ")
    main_module = reload_main()
    app = main_module.create_app(enable_rate_limit=False)

    entry = _find_cors_middleware(app)
    assert entry.kwargs["allow_origins"] == ["*"]
    assert entry.kwargs["allow_credentials"] is False
