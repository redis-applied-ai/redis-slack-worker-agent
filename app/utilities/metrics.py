import logging
from typing import Optional

logger = logging.getLogger(__name__)


def setup_metrics():
    """No-op metrics setup. OpenTelemetry collector has been removed."""
    logger.info("Telemetry disabled; skipping metrics setup")
    return None


def get_meter() -> Optional[object]:
    """No-op meter getter."""
    return None


class OpenAITokenMetrics:
    """No-op metrics tracker for OpenAI token usage."""

    def __init__(self):
        logger.debug("Telemetry disabled; OpenAITokenMetrics is a no-op")

    def record_answer_completion(self, model: str, total_tokens: int, tool_calls: int):
        logger.debug(
            "No-op metrics: model=%s tokens=%s tool_calls=%s",
            model,
            total_tokens,
            tool_calls,
        )


# Global metrics instance
_token_metrics: Optional[OpenAITokenMetrics] = None


def get_token_metrics() -> Optional[OpenAITokenMetrics]:
    """Return None to disable metrics recording paths in calling code."""
    return None
