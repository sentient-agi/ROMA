import socket

import pytest

from roma_dspy.core.observability import span_manager as span_module


@pytest.fixture(autouse=True)
def _clear_span_env(monkeypatch):
    """Ensure environment toggles do not leak between tests."""
    monkeypatch.delenv("MLFLOW_ENABLED", raising=False)
    monkeypatch.delenv("ROMA_DISABLE_MLFLOW_SPANS", raising=False)


def _force_mlflow_available(monkeypatch):
    """Force span manager to behave as if MLflow is installed."""
    monkeypatch.setattr(span_module, "MLFLOW_AVAILABLE", True)
    monkeypatch.setattr(span_module, "start_span", object())


def test_span_manager_disables_for_unresolvable_host(monkeypatch):
    _force_mlflow_available(monkeypatch)

    def fake_getaddrinfo(host: str, port: int):
        raise socket.gaierror()

    monkeypatch.setattr(span_module.socket, "getaddrinfo", fake_getaddrinfo)

    manager = span_module.ROMASpanManager(
        enabled=True,
        tracking_uri="http://mlflow:5000",
    )

    assert manager.enabled is False


def test_span_manager_disables_via_env_toggle(monkeypatch):
    _force_mlflow_available(monkeypatch)
    monkeypatch.setenv("MLFLOW_ENABLED", "false")
    monkeypatch.setattr(
        span_module.socket,
        "getaddrinfo",
        lambda host, port: [
            (socket.AF_UNSPEC, socket.SOCK_STREAM, 0, "", (host, port))
        ],
    )

    manager = span_module.ROMASpanManager(
        enabled=True,
        tracking_uri="http://localhost:5000",
    )

    assert manager.enabled is False


def test_span_manager_allows_localhost_without_dns(monkeypatch):
    _force_mlflow_available(monkeypatch)

    manager = span_module.ROMASpanManager(
        enabled=True,
        tracking_uri="http://localhost:5000",
    )

    assert manager.enabled is True
