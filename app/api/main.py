"""
Main FastAPI application entry point.

This module creates and configures the FastAPI application with all routers and middleware.
"""

import logging
import os
from contextlib import asynccontextmanager

from docket.docket import Docket
from dotenv import load_dotenv
from fastapi import FastAPI

# Load environment variables from .env file
load_dotenv()

from app.agent.tasks import (
    evaluate_bump_context,
    get_bot_user_id,
    get_thread_context,
    process_slack_question_with_retry,
    track_thread_participation,
    update_answer_feedback,
)
from app.api.auth import callback, content_page, debug_callback_url, home, login, logout
from app.api.slack_app import get_slack_app
from app.utilities import keys
from app.utilities.environment import get_env_var
from app.utilities.logging_config import (
    configure_uvicorn_logging,
    ensure_stdout_logging,
)
from app.utilities.telemetry import setup_telemetry
from app.worker.task_registration import register_all_tasks

from .routers import content, health, slack


# Get Redis URL dynamically
def get_redis_url() -> str:
    redis_url = get_env_var("REDIS_URL", "redis://localhost:6379/0")
    logger.debug("Main app Redis connection configured")
    return redis_url


logger = logging.getLogger(__name__)


async def process_haink_mention(
    user: str,
    text: str,
    channel: str,
    thread_ts: str | None = None,
    message_ts: str | None = None,
):
    """Core logic for processing Haink mentions/triggers - shared by app mentions and name-only triggers."""

    # Track that Haink has been mentioned in this thread
    if thread_ts:  # Only track if we have a valid thread timestamp
        await track_thread_participation(channel, thread_ts)

    # Check for "bump" - mention with minimal/no additional text
    bot_user_id = await get_bot_user_id()
    mention_text = f"<@{bot_user_id}>"
    remaining_text = text.replace(mention_text, "").strip()

    # For name-only triggers, treat them as bumps if they're just the name
    if mention_text not in text:
        # This is a name-only trigger like "Haink"
        clean_text = text.strip().rstrip("!?.,").lower()
        if clean_text == "haink":
            # Treat name-only "Haink" as a bump
            remaining_text = ""
        else:
            remaining_text = text.strip()

    # If it's just a mention or very short text, treat as a "bump"
    if len(remaining_text) <= 3:  # Just punctuation, spaces, or very short
        logger.info(f"Detected 'bump' from user {user} in thread {thread_ts}")

        # Analyze thread context to see if we should respond
        thread_context = (
            await get_thread_context(channel, thread_ts) if thread_ts else []
        )

        # Look for recent unanswered questions or technical discussions
        should_bump_respond = await evaluate_bump_context(thread_context)

        if should_bump_respond:
            # Create a context-aware response based on the thread
            # Make bump keys unique by including timestamp to avoid cache hits
            import time

            bump_text = f"Looking at the thread context to see how I can help... (bump_{int(time.time())})"
            question_key = keys.question_key(user, bump_text, message_ts)

            async with Docket(url=get_redis_url()) as docket:
                await docket.add(process_slack_question_with_retry, key=question_key)(
                    user_id=user,
                    text=bump_text,
                    channel_id=channel,
                    thread_ts=thread_ts,
                )
        else:
            # Make bump keys unique by including timestamp to avoid cache hits
            import time

            bump_text = (
                f"I'm not sure how to help. Can you say more? (bump_{int(time.time())})"
            )
            question_key = keys.question_key(user, bump_text, message_ts)
            async with Docket(url=get_redis_url()) as docket:
                await docket.add(process_slack_question_with_retry, key=question_key)(
                    user_id=user,
                    text=bump_text,
                    channel_id=channel,
                    thread_ts=thread_ts,
                )
            logger.info(
                f"Bump detected but no clear need to respond in thread {thread_ts}"
            )
        return

    # Regular mention with actual content - process normally
    question_key = keys.question_key(user, text, message_ts)

    # Schedule main processing task with retry
    redis_url = get_redis_url()
    logger.debug("Main app processing Slack mention")
    async with Docket(name="applied-ai-agent", url=redis_url) as docket:
        await docket.add(process_slack_question_with_retry, key=question_key)(
            user_id=user, text=text, channel_id=channel, thread_ts=thread_ts
        )


async def handle_app_mentions(body, say, ack):
    """Enhanced app mention handler with retry, follow-up scheduling, and 'bump' detection."""
    await ack()

    user = body["event"]["user"]
    text = body["event"]["text"]
    channel = body["event"]["channel"]
    thread_ts = body["event"].get("thread_ts")
    message_ts = body["event"].get("ts")

    # For app mentions in channels, ensure we create/respond in thread
    # If there's no existing thread_ts, we'll use the message timestamp to create a thread
    if not thread_ts:
        # Use the message timestamp as thread_ts to create a thread on the original mention
        thread_ts = body["event"]["ts"]

    # Use shared processing logic
    await process_haink_mention(user, text, channel, thread_ts, message_ts)


async def handle_message_events(body, say, ack, logger):
    """Handle both DM messages and thread messages for thread awareness."""
    await ack()

    event = body.get("event", {})
    message_text = event.get("text", "")
    channel_type = event.get("channel_type")
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts")
    user_id = event.get("user")
    message_text = event.get("text", "")

    # Skip if this is from a bot or has no text
    if event.get("bot_id") or not message_text:
        return

    # Get bot user ID for filtering
    bot_user_id = await get_bot_user_id()

    # Skip if this is Haink's own message
    if user_id == bot_user_id:
        return

    # Case 1: Handle DM messages (existing functionality)
    if channel_type == "im" or channel.startswith("D"):
        # Also ignore messages that have subtypes we don't want to handle
        if event.get("subtype") and event.get("subtype") not in [
            None,
            "bot_message",
            "thread_broadcast",
            "file_share",
        ]:
            logger.debug(f"Ignoring message with subtype: {event.get('subtype')}")
            return

        logger.info(f"Handling DM message: {body}")

        question_key = keys.question_key(user_id, message_text, event.get("ts"))

        # For DMs, if there's no existing thread_ts, use the message timestamp for threading
        if not thread_ts:
            thread_ts = event.get("ts")

        redis_url = get_redis_url()
        logger.debug("Main app processing DM")
        async with Docket(name="applied-ai-agent", url=redis_url) as docket:
            await docket.add(process_slack_question_with_retry, key=question_key)(
                user_id=user_id,
                text=message_text,
                channel_id=channel,
                thread_ts=thread_ts,
            )
        return

    # Case 2: Handle thread messages - Check for name-only trigger
    if thread_ts:
        # Skip if user mentions Haink (handled by app_mention)
        if f"<@{bot_user_id}>" in message_text:
            logger.info(
                f"Skipping thread message because Haink is mentioned: {message_text}"
            )
            return

        # Check if this is just "Haink" by itself (name-only trigger)
        # Strip whitespace and common punctuation
        clean_text = message_text.strip().rstrip("!?.,").lower()

        if clean_text == "haink":
            logger.info(
                f"Name-only trigger detected: '{message_text}' -> treating as @ mention"
            )

            # Call the core mention processing logic directly
            await process_haink_mention(
                user_id, message_text, channel, thread_ts, event.get("ts")
            )

            return

        # SIMPLIFIED: Haink only responds to @ mentions or name-only triggers
        logger.debug(f"Ignoring thread message (no trigger): {message_text[:50]}...")
        return

    # Case 3: Ignore other channel messages that aren't DMs or in threads
    logger.debug(f"Ignoring non-DM, non-thread message in channel {channel}")


# Backward compatibility alias for tests
handle_dm_messages = handle_message_events


async def handle_feedback_action(ack, body, logger):
    """Handle thumbs up/down feedback button actions."""
    await ack()

    try:
        logger.info(f"Received feedback action: {body}")

        # Extract action details
        action = body.get("actions", [{}])[0]
        action_id = action.get("action_id")
        value = action.get("value")

        # Extract user and message details
        user_id = body.get("user", {}).get("id")
        message = body.get("message", {})
        thread_ts = message.get("thread_ts") or message.get("ts")

        # Fix: Get channel_id from the correct location in interactive payload
        channel_id = body.get("channel", {}).get("id") or body.get("channel", "")

        logger.info(
            f"Feedback action - user_id: {user_id}, channel_id: {channel_id}, thread_ts: {thread_ts}"
        )
        logger.info(f"Action details - action_id: {action_id}, value: {value}")

        # Determine if it's thumbs up or down and extract the answer key
        accepted = value.startswith("thumbs_up")
        answer_key = value.split(":", 1)[1] if ":" in value else ""

        if not answer_key:
            logger.warning(f"No answer key found in feedback value: {value}")
            return

        logger.info(
            f"Feedback received: user={user_id}, accepted={accepted}, thread={thread_ts}, answer_key={answer_key}"
        )

        # Schedule the feedback update task
        feedback_key = keys.feedback_key(user_id, thread_ts)

        async with Docket(url=get_redis_url()) as docket:
            await docket.add(update_answer_feedback, key=feedback_key)(
                answer_key=answer_key,
                accepted=accepted,
            )

        # Update the message to show feedback was received
        feedback_text = (
            "👍 Thanks for the feedback!" if accepted else "👎 Thanks for the feedback!"
        )

        # Preserve original blocks if present, else fallback to section block
        original_blocks = message.get("blocks")
        if original_blocks:
            updated_blocks = original_blocks + [
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": feedback_text}],
                }
            ]
        else:
            updated_blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message.get("text", "")},
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": feedback_text}],
                },
            ]

        await get_slack_app().client.chat_update(
            channel=channel_id,
            ts=message.get("ts"),
            text=message.get("text", ""),
            blocks=updated_blocks,
        )

        logger.info("Successfully updated message with feedback acknowledgment")

    except Exception as e:
        logger.error(f"Error handling feedback action: {e}")
        logger.error(f"Full body: {body}")
        # Don't re-raise - we don't want to break the user experience


async def setup_slack_app():
    app = get_slack_app()
    app.event("app_mention")(handle_app_mentions)
    # Handle both DMs and thread messages with thread awareness
    app.event("message")(handle_message_events)
    # Handle interactive button actions
    app.action("feedback_thumbs_up")(handle_feedback_action)
    app.action("feedback_thumbs_down")(handle_feedback_action)
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager."""
    print("Starting up FastAPI application with Docket...")

    # Ensure logs go to stdout with a sane default
    ensure_stdout_logging()

    # Log LLM provider/model at API startup for visibility
    try:
        provider = os.getenv("LLM_PROVIDER", "bedrock").lower()
        if provider == "bedrock":
            model = os.getenv(
                "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"
            )
        else:
            model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1")
        logger.info(f"LLM configured: provider={provider} model={model} (api)")
    except Exception as e:
        logger.warning(f"Could not determine LLM provider/model on API startup: {e}")

    try:
        await setup_slack_app()

        # Always register tasks - API needs to know what tasks exist for dispatching
        print("🔧 Registering tasks for API dispatching")
        await register_all_tasks()

        setup_telemetry(app)
        print("✅ API startup completed successfully")
    except Exception as e:
        print(f"⚠️ Warning: Startup had issues but continuing: {e}")
        # Don't fail completely - let the app start for health checks

    yield

    logger.info("Shutting down FastAPI application...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Advanced Slack RAG Bot with Docket",
        description="A Slack bot with advanced background processing, retries, and scheduling",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure uvicorn logging to suppress health check logs
    configure_uvicorn_logging()

    # Include routers
    app.include_router(health.router)
    app.include_router(content.router)
    app.include_router(slack.router)

    # Auth routes (unprotected)
    app.add_api_route("/", home, methods=["GET"], name="home")
    app.add_api_route("/login", login, methods=["GET"], name="login")
    app.add_api_route("/callback", callback, methods=["GET"], name="callback")
    app.add_api_route("/logout", logout, methods=["GET"], name="logout")
    app.add_api_route("/content", content_page, methods=["GET"], name="content")
    app.add_api_route(
        "/debug/callback-url",
        debug_callback_url,
        methods=["GET"],
        name="debug_callback_url",
    )

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api.main:app", host="0.0.0.0", port=3000, reload=True, log_level="info"
    )
