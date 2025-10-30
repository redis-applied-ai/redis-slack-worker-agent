"""
Custom logging configuration for the application.

This module provides utilities to configure logging, including filtering out
health check access logs to prevent log spam.
"""

import logging
import os
import sys
from typing import List


class HealthCheckFilter(logging.Filter):
    """
    Logging filter to suppress access logs for health check endpoints.

    This filter prevents health check 200 responses from cluttering the logs
    while preserving all other access logs.
    """

    def __init__(self, health_check_paths: List[str] = None):
        super().__init__()
        self.health_check_paths = health_check_paths or ["/health", "/health/detailed"]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter out health check access logs.

        Args:
            record: The log record to filter

        Returns:
            True if the record should be logged, False if it should be suppressed
        """
        # Check if this is an access log record
        if hasattr(record, "name") and "uvicorn.access" in record.name:
            # Check if this is a health check request
            if hasattr(record, "args") and record.args:
                # Extract the path from the log record
                # uvicorn access log format includes the request line
                if len(record.args) > 4:
                    request_line = record.args[4]
                    if request_line and isinstance(request_line, str):
                        # Extract path from request line (e.g., "GET /health HTTP/1.1")
                        parts = request_line.split()
                        if len(parts) >= 2:
                            path = parts[1]
                            # Suppress logging if it's a health check
                            if any(
                                path.startswith(health_path)
                                for health_path in self.health_check_paths
                            ):
                                return False

            # Also check the message content for health check paths
            if hasattr(record, "getMessage"):
                message = record.getMessage()
                if any(
                    health_path in message for health_path in self.health_check_paths
                ):
                    return False

        # Allow all other logs to pass through
        return True


def setup_health_check_log_filter():
    """
    Set up the health check log filter for uvicorn access logs.

    This function configures the logging system to suppress health check
    access logs while preserving all other access logs.
    """
    # Get the uvicorn access logger
    access_logger = logging.getLogger("uvicorn.access")

    # Add our custom filter
    health_filter = HealthCheckFilter()
    access_logger.addFilter(health_filter)

    # Also apply to the root logger in case uvicorn logs through it
    root_logger = logging.getLogger()
    if health_filter not in root_logger.filters:
        root_logger.addFilter(health_filter)


def ensure_stdout_logging(level: int | str | None = None) -> None:
    """Ensure logs are emitted to stdout with a sensible default formatter.

    This function is safe to call multiple times. It will add a StreamHandler
    to sys.stdout if one is not already present and set the root log level.
    """
    try:
        root = logging.getLogger()
        # Determine level from env if not provided
        if level is None:
            level_env = os.getenv("LOG_LEVEL", "INFO").upper()
            try:
                level = getattr(logging, level_env)
            except AttributeError:
                level = logging.INFO
        elif isinstance(level, str):
            try:
                level = getattr(logging, level.upper())
            except AttributeError:
                level = logging.INFO

        # Check if a stdout handler already exists
        has_stdout = False
        for h in root.handlers:
            if (
                isinstance(h, logging.StreamHandler)
                and getattr(h, "stream", None) is sys.stdout
            ):
                has_stdout = True
                break

        if not has_stdout:
            handler = logging.StreamHandler(stream=sys.stdout)
            formatter = logging.Formatter(
                fmt="%(asctime)s %(name)s %(levelname)5s  %(message)s",
                datefmt="%H:%M:%S",
            )
            handler.setFormatter(formatter)
            root.addHandler(handler)

        # Set level on root
        root.setLevel(level)
    except Exception as e:
        # As a last resort, don't crash if logging config fails
        print(f"⚠️ Warning: Failed to ensure stdout logging: {e}")


def configure_uvicorn_logging():
    """
    Configure uvicorn logging with health check filtering.

    This is a more robust approach that works with uvicorn's logging system.
    """
    try:
        setup_health_check_log_filter()
        print("✅ Health check log filtering configured")
    except Exception as e:
        print(f"⚠️ Warning: Failed to configure health check log filtering: {e}")
        # Don't fail the application if logging configuration fails
