import logging

from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.app.async_app import AsyncApp

from app.utilities.environment import get_env_var

_slack_app: AsyncApp | None = None
_handler: AsyncSlackRequestHandler | None = None

logger = logging.getLogger(__name__)


def get_handler() -> AsyncSlackRequestHandler:
    global _handler
    if _handler is None:
        _handler = AsyncSlackRequestHandler(get_slack_app())
    return _handler


def get_slack_app() -> AsyncApp:
    global _slack_app

    if _slack_app is None:
        _slack_app = AsyncApp(
            token=get_env_var("SLACK_BOT_TOKEN"),
            signing_secret=get_env_var("SLACK_SIGNING_SECRET"),
            # Disable installation store to prevent Redis connection attempts
            installation_store=None,
            # For single workspace apps, we don't need multi-team features
            oauth_settings=None,
        )
    return _slack_app
