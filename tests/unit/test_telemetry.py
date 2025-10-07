from unittest.mock import MagicMock, patch

from app.utilities.telemetry import setup_telemetry


def test_telemetry_setup_without_endpoint():
    """Test that telemetry setup is skipped when OTLP_ENDPOINT is not set."""
    with patch.dict("os.environ", {}, clear=True):
        # Should not raise any exceptions
        setup_telemetry()


def test_telemetry_setup_with_endpoint():
    """Test that telemetry setup works when OTLP_ENDPOINT is set."""
    with patch.dict("os.environ", {"OTLP_ENDPOINT": "http://localhost:4318/v1/traces"}):
        # Should not raise any exceptions
        setup_telemetry()


def test_telemetry_setup_with_fastapi_app():
    """Test that telemetry setup works with FastAPI app."""
    mock_app = MagicMock()

    with patch.dict("os.environ", {"OTLP_ENDPOINT": "http://localhost:4318/v1/traces"}):
        # Should not raise any exceptions
        setup_telemetry(mock_app)
