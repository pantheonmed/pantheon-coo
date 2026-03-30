"""
monitoring/tracing.py — OpenTelemetry tracer setup and span helper.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

_tracer: Optional[Any] = None


def init_tracing(service_name: Optional[str] = None) -> None:
    global _tracer
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    from config import settings

    name = service_name or settings.otel_service_name
    provider = TracerProvider()
    endpoint = (settings.otel_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        except Exception:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(name)


def get_tracer():
    return _tracer


@contextmanager
def span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in (attributes or {}).items():
            try:
                s.set_attribute(k, str(v))
            except Exception:
                pass
        yield s
