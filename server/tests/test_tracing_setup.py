"""setup_tracing hands CodeMonet's settings to Platform's shared tracing bootstrap."""

from typing import Any

import pytest
from fastapi import FastAPI
from fenton_service.telemetry import TracingSettings, TracingStatus

from code_monet import tracing


def test_tracing_stays_off_unless_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(tracing, "configure_tracing", lambda *a, **_: calls.append(a))
    monkeypatch.setattr(tracing.settings, "otel_enabled", False)

    assert tracing.setup_tracing(FastAPI()) is TracingStatus.DISABLED
    assert calls == []


def test_enabled_tracing_exports_xray_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _configure(app: Any, settings: TracingSettings) -> TracingStatus:
        seen.update(app=app, settings=settings)
        return TracingStatus.ENABLED

    app = FastAPI()
    monkeypatch.setattr(tracing, "configure_tracing", _configure)
    monkeypatch.setattr(tracing.settings, "otel_enabled", True)
    monkeypatch.setattr(tracing.settings, "dev_mode", False)
    monkeypatch.setattr(tracing.settings, "otel_service_name", "drawing-agent")
    monkeypatch.setattr(tracing.settings, "otel_exporter_endpoint", "http://otel-collector:4318")

    assert tracing.setup_tracing(app) is TracingStatus.ENABLED
    assert seen["app"] is app
    assert seen["settings"] == TracingSettings(
        service_name="drawing-agent",
        service_version="1.0.0",
        environment="production",
        otlp_endpoint="http://otel-collector:4318",
        excluded_paths=("/health",),
        xray=True,
    )
