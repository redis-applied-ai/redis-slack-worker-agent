import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.utilities.metrics import setup_metrics

logger = logging.getLogger(__name__)


def setup_telemetry(app=None):
    """Set up OpenTelemetry instrumentation for FastAPI and OpenAI."""

    # Get OTLP endpoint from environment
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.info("OTLP_ENDPOINT not set, skipping telemetry setup")
        return

    try:
        # Set up trace provider
        trace_provider = TracerProvider()

        # Set up OTLP exporter with correct endpoint for traces
        trace_endpoint = f"{otlp_endpoint}/v1/traces"
        otlp_exporter = OTLPSpanExporter(endpoint=trace_endpoint)

        # Add batch span processor
        trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Set the trace provider
        trace.set_tracer_provider(trace_provider)

        # Set up metrics with correct endpoint
        setup_metrics()
        logger.info("Metrics setup enabled")

        # Instrument FastAPI if app is provided
        if app:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumentation enabled")

        # Enable OpenAI instrumentator for automatic instrumentation
        # This will provide automatic spans and some basic metrics
        OpenAIInstrumentor().instrument()
        logger.info("OpenAI instrumentation enabled")

        logger.info(f"Telemetry setup complete with OTLP endpoint: {otlp_endpoint}")

    except Exception as e:
        logger.error(f"Failed to setup telemetry: {e}")
        # Don't fail the application if telemetry setup fails
