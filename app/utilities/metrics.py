import logging
import os
from typing import Optional

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

logger = logging.getLogger(__name__)

# Global meter instance
_meter: Optional[metrics.Meter] = None
_metric_reader: Optional[PeriodicExportingMetricReader] = None


def setup_metrics():
    """Set up OpenTelemetry metrics with OTLP exporter."""
    global _meter, _metric_reader

    # Get OTLP endpoint from environment
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.info("OTLP_ENDPOINT not set, skipping metrics setup")
        return None

    try:
        # Create metric reader with OTLP exporter using correct endpoint for metrics
        metrics_endpoint = f"{otlp_endpoint}/v1/metrics"
        logger.info(f"Setting up metrics with endpoint: {metrics_endpoint}")

        otlp_exporter = OTLPMetricExporter(endpoint=metrics_endpoint)
        _metric_reader = PeriodicExportingMetricReader(
            exporter=otlp_exporter,
            export_interval_millis=1000,  # Export every 1 second for testing
        )

        # Create meter provider
        meter_provider = MeterProvider(metric_readers=[_metric_reader])
        metrics.set_meter_provider(meter_provider)

        # Create meter
        _meter = metrics.get_meter(__name__)

        logger.info(f"Metrics setup complete. Meter: {_meter}")

        return _meter

    except Exception as e:
        logger.error(f"Failed to setup metrics: {e}")
        return None


def get_meter() -> Optional[metrics.Meter]:
    """Get the global meter instance."""
    global _meter
    if _meter is None:
        _meter = setup_metrics()
    return _meter


class OpenAITokenMetrics:
    """Simplified metrics for tracking OpenAI token usage and tool calls per answer."""

    def __init__(self):
        self.meter = get_meter()
        if not self.meter:
            logger.warning("No meter available for OpenAITokenMetrics")
            return

        # Create counter for total answers generated
        self.answers_counter = self.meter.create_counter(
            name="app.answers_total",
            description="Total number of answers generated",
            unit="answers",
        )

        # Create counter for total tokens used per answer
        self.tokens_per_answer_counter = self.meter.create_counter(
            name="app.tokens_per_answer",
            description="Total tokens used per answer",
            unit="tokens",
        )

        # Create counter for tool calls per answer
        self.tool_calls_per_answer_counter = self.meter.create_counter(
            name="app.tool_calls_per_answer",
            description="Total tool calls made per answer",
            unit="calls",
        )

        logger.info("OpenAITokenMetrics initialized successfully")

    def record_answer_completion(self, model: str, total_tokens: int, tool_calls: int):
        """Record metrics for a completed answer."""
        if not self.meter:
            logger.warning("No meter available for recording answer completion")
            return

        # Track answer completion with model as attribute
        model_attrs = {"model": model}

        # Record answer count
        self.answers_counter.add(1, model_attrs)
        logger.info(f"Recorded answer completion for model: {model}")

        # Record total tokens for this answer
        self.tokens_per_answer_counter.add(total_tokens, model_attrs)
        logger.info(f"Recorded {total_tokens} tokens for model {model}")

        # Record tool calls for this answer
        self.tool_calls_per_answer_counter.add(tool_calls, model_attrs)
        logger.info(f"Recorded {tool_calls} tool calls for model {model}")


# Global metrics instance
_token_metrics: Optional[OpenAITokenMetrics] = None


def get_token_metrics() -> Optional[OpenAITokenMetrics]:
    """Get the global token metrics instance."""
    global _token_metrics
    if _token_metrics is None:
        _token_metrics = OpenAITokenMetrics()
    return _token_metrics
