"""OpenTelemetry bootstrap and span helpers. One `setup_otel` call per service."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger(__name__)

DISABLED_ENDPOINTS = {"none", "off", "disabled", ""}
DEFAULT_ENDPOINT = "http://otel-collector:4318"


CORRELATION_HEADER = "x-correlation-id"


class CorrelationIdSpanProcessor(SpanProcessor):
    """Copy `correlation_id` from the parent span onto every new span.

    Framework spans (FastAPI >= 0.16x traces requests itself) and library
    spans never set our attribute; inheriting it at start keeps the rule
    "every span of a request carries correlation_id" true for all of them.
    """

    def on_start(self, span, parent_context: Context | None = None) -> None:
        parent = trace.get_current_span(parent_context)
        attrs = getattr(parent, "attributes", None)
        if attrs:
            value = attrs.get("correlation_id")
            if isinstance(value, str) and value:
                span.set_attribute("correlation_id", value)

    def on_end(self, span) -> None:  # pragma: no cover - nothing to do
        return None

    def shutdown(self) -> None:  # pragma: no cover
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # pragma: no cover
        return True


def resolve_endpoint(config_endpoint: str | None = None) -> str:
    """`OTEL_EXPORTER_OTLP_ENDPOINT` wins; then `telemetry.otlp_endpoint`; then the default."""
    env = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if env is not None:
        return env
    if config_endpoint is not None:
        return config_endpoint
    return DEFAULT_ENDPOINT


def export_disabled(endpoint: str) -> bool:
    return endpoint.strip().lower() in DISABLED_ENDPOINTS


def setup_otel(
    service_name: str,
    namespace: str = "opencg",
    *,
    config_endpoint: str | None = None,
) -> trace.Tracer:
    """Initialise the global tracer provider and return a tracer for the caller.

    Set `OTEL_EXPORTER_OTLP_ENDPOINT` to `none`, `off`, `disabled` or empty for
    fully offline runs (no exporter is wired in that case). When the env var is
    unset, `config_endpoint` (from `telemetry.otlp_endpoint`) is used.
    """
    endpoint = resolve_endpoint(config_endpoint)
    resource = Resource.create({"service.name": service_name, "service.namespace": namespace})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(CorrelationIdSpanProcessor())
    if not export_disabled(endpoint):
        try:
            exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as exc:
            log.warning("OTel exporter init failed: %s", exc)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def extract_context(headers: Mapping[str, str]) -> Context | None:
    """Parent context for a request's root span.

    When a framework span is already active (FastAPI traces requests itself
    and has continued the caller's `traceparent`), return None so our span
    nests under it. Otherwise extract W3C `traceparent`/`tracestate` from the
    incoming headers.
    """
    if trace.get_current_span().get_span_context().is_valid:
        return None
    return propagate.extract(dict(headers))


def tag_request_span(correlation_id: str | None) -> None:
    """Put `correlation_id` on the active (framework) request span."""
    if not correlation_id:
        return
    span = trace.get_current_span()
    if span.get_span_context().is_valid and span.is_recording():
        span.set_attribute("correlation_id", correlation_id)


@contextmanager
def stage_span(
    tracer: trace.Tracer,
    name: str,
    correlation_id: str | None,
    *,
    context: Context | None = None,
    **attributes: Any,
) -> Iterator[trace.Span]:
    """Start a span that always carries `correlation_id`."""
    with tracer.start_as_current_span(name, context=context) as span:
        if correlation_id:
            span.set_attribute("correlation_id", correlation_id)
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


def current_correlation_id() -> str | None:
    """`correlation_id` of the current span, if it set one (SDK spans only)."""
    span = trace.get_current_span()
    attrs = getattr(span, "attributes", None)
    if attrs:
        value = attrs.get("correlation_id")
        if isinstance(value, str):
            return value
    return None
