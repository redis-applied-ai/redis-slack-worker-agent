import logging
import os
import sys

import pytest

from app.utilities.logging_config import ensure_stdout_logging


def _count_stdout_handlers():
    root = logging.getLogger()
    return sum(
        1
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stdout
    )


def test_ensure_stdout_logging_adds_stdout_handler(monkeypatch):
    # Preserve current state
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    try:
        # Start clean
        for h in list(root.handlers):
            root.removeHandler(h)
        assert _count_stdout_handlers() == 0

        # Set LOG_LEVEL to DEBUG to exercise env path
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        ensure_stdout_logging()

        # Should add exactly one stdout handler and set level to DEBUG
        assert _count_stdout_handlers() == 1
        assert root.level == logging.DEBUG

        # Emitting a log should not crash
        logging.getLogger(__name__).info("hello")
    finally:
        # Restore state
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in old_handlers:
            root.addHandler(h)
        root.setLevel(old_level)


def test_ensure_stdout_logging_is_idempotent(monkeypatch):
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    try:
        for h in list(root.handlers):
            root.removeHandler(h)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        ensure_stdout_logging()
        first_count = _count_stdout_handlers()
        ensure_stdout_logging()
        second_count = _count_stdout_handlers()

        assert first_count == 1
        assert second_count == 1
        # Default level is INFO when LOG_LEVEL not set
        assert root.level == logging.INFO
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in old_handlers:
            root.addHandler(h)
        root.setLevel(old_level)

