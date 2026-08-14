"""OpenTelemetry tracing (optional via OTEL_ENABLED)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging_config import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.core.config import Settings

logger = get_logger(__name__)

_tracing_configured = False


def setup_telemetry(app: FastAPI, settings: Settings) -> None:
    """Install OTLP tracing when OTEL_ENABLED=true."""
    global _tracing_configured
    if not settings.otel_enabled or _tracing_configured:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("otel_import_failed", error=str(exc))
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")
    _tracing_configured = True
    logger.info(
        "otel_enabled",
        service=settings.otel_service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
    )


def shutdown_telemetry() -> None:
    global _tracing_configured
    if not _tracing_configured:
        return
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception as exc:  # noqa: BLE001
        logger.warning("otel_shutdown_failed", error=str(exc))
    finally:
        _tracing_configured = False
