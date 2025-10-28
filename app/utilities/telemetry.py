import logging

logger = logging.getLogger(__name__)


def setup_telemetry(app=None):
    """No-op telemetry setup. OpenTelemetry collector has been removed."""
    logger.info("Telemetry disabled; skipping OpenTelemetry setup")
    return
