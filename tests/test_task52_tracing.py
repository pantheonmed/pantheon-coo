"""Task 52 — OpenTelemetry tracing helpers."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import monitoring.tracing as tr


@pytest.fixture(autouse=True)
def _reset_tracer_singleton():
    yield
    tr._tracer = None


def test_get_tracer_none_before_init():
    tr._tracer = None
    assert tr.get_tracer() is None


def test_init_tracing_does_not_crash():
    tr._tracer = None
    fake_tracer = MagicMock()
    with patch("opentelemetry.sdk.trace.TracerProvider"):
        with patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"):
            with patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter"):
                with patch("opentelemetry.trace.set_tracer_provider"):
                    with patch("opentelemetry.trace.get_tracer", return_value=fake_tracer):
                        tr.init_tracing(service_name="test-pantheon")
    assert tr.get_tracer() is fake_tracer


def test_span_noop_when_tracer_none():
    tr._tracer = None
    with tr.span("x", {"a": "1"}) as s:
        assert s is None


def test_span_works_when_tracer_set():
    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_span)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_tracer.start_as_current_span = MagicMock(return_value=mock_cm)
    tr._tracer = mock_tracer
    with tr.span("inner", {"k": "v"}) as s:
        assert s is mock_span


def test_otel_packages_in_requirements():
    root = Path(__file__).resolve().parents[1]
    txt = (root / "requirements.txt").read_text()
    assert "opentelemetry-api==1.24.0" in txt
    assert "opentelemetry-sdk==1.24.0" in txt
