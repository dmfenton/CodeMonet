"""OpenTelemetry tracing configuration for AWS X-Ray."""

import logging
from typing import Any

from fenton_service.telemetry import TracingSettings, TracingStatus, configure_tracing
from opentelemetry import trace

from code_monet.config import settings

logger = logging.getLogger(__name__)


def setup_tracing(app: Any) -> TracingStatus:
    """Trace the app through Platform's shared bootstrap, exporting X-Ray-compatible spans."""
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing disabled (set OTEL_ENABLED=true to enable)")
        return TracingStatus.DISABLED
    return configure_tracing(
        app,
        TracingSettings(
            service_name=settings.otel_service_name,
            service_version="1.0.0",
            environment="development" if settings.dev_mode else "production",
            otlp_endpoint=settings.otel_exporter_endpoint,
            excluded_paths=("/health",),
            xray=True,
        ),
    )


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for manual instrumentation.

    Args:
        name: Name for the tracer (typically module name)

    Returns:
        Tracer instance
    """
    return trace.get_tracer(name)


def get_current_trace_id() -> str | None:
    """Get the current trace ID if available.

    Returns:
        Trace ID as hex string, or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return None


def record_client_spans(spans: list[dict[str, Any]]) -> int:
    """Record spans received from mobile/web clients.

    Converts client span data to OpenTelemetry spans and exports them.

    Args:
        spans: List of span dicts from client with keys:
            - traceId: X-Ray format trace ID
            - spanId: 16 hex char span ID
            - name: Span name
            - startTime: Unix timestamp in ms
            - endTime: Unix timestamp in ms (optional)
            - attributes: Dict of attributes
            - status: 'ok' or 'error'
            - error: Error message (optional)

    Returns:
        Number of spans recorded
    """
    if not settings.otel_enabled:
        return 0

    tracer = get_tracer("mobile-client")
    recorded = 0

    for span_data in spans:
        try:
            # Create span with client-provided name and attributes
            name = span_data.get("name", "unknown")
            attributes = span_data.get("attributes", {})

            # Add client trace/span IDs as attributes for correlation
            attributes["client.trace_id"] = span_data.get("traceId", "")
            attributes["client.span_id"] = span_data.get("spanId", "")
            attributes["client.source"] = "mobile"

            # Calculate duration
            start_time = span_data.get("startTime", 0)
            end_time = span_data.get("endTime", start_time)
            duration_ms = end_time - start_time if end_time else 0
            attributes["duration_ms"] = duration_ms

            # Create the span
            with tracer.start_as_current_span(
                name,
                kind=trace.SpanKind.CLIENT,
            ) as span:
                # Set attributes
                for key, value in attributes.items():
                    if isinstance(value, str | int | float | bool):
                        span.set_attribute(key, value)

                # Set error status if applicable
                if span_data.get("status") == "error":
                    error_msg = span_data.get("error", "Unknown error")
                    span.set_status(trace.Status(trace.StatusCode.ERROR, error_msg))

            recorded += 1

        except Exception as e:
            logger.warning(f"Failed to record client span: {e}")

    return recorded
