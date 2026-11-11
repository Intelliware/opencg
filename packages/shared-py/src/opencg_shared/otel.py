"""OpenTelemetry bootstrap. One call per service at startup."""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger(__name__)


def setup_otel(service_name: str, namespace: str = "opencg") -> trace.Tracer:
    """Initialise the global tracer provider and return a tracer for the caller.

    Env-var-driven so the same call works in compose, in tests, and locally.
    Set `OTEL_EXPORTER_OTLP_ENDPOINT` to disable by setting it to `none` for
    fully offline runs (no exporter is wired in that case).
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": namespace,
        }
    )
    provider = TracerProvider(resource=resource)
    if endpoint.lower() not in {"none", "off", "disabled", ""}:
        try:
            exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as exc:
            log.warning("OTel exporter init failed: %s", exc)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
