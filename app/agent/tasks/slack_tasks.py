"""
Slack-related tasks for the applied-ai-agent.

This module contains all tasks related to Slack integration, message processing, and user interactions.
"""

import hashlib
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from docket import Retry
from ulid import ULID

from app.agent.core import answer_question, is_brief_satisfied_response
from app.api.slack_app import get_slack_app
from app.utilities import keys
from app.utilities.database import (
    get_answer_index,
    get_document_index,
    get_redis_client,
    get_vectorizer,
)
from app.utilities.environment import get_env_var

logger = logging.getLogger(__name__)


# Get REDIS_URL dynamically
def get_redis_url() -> str:
    return get_env_var("REDIS_URL", "redis://localhost:6379/0")


async def get_thread_context(channel_id: str, thread_ts: str) -> list[dict]:
    """
    Gather all messages in a thread for context.
    Returns a list of message dictionaries with 'user' and 'text' keys.
    """
    slack_app = get_slack_app()
    thread_context = []

    try:
        # Get conversation replies (thread messages)
        result = await slack_app.client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=50,  # Reasonable limit to avoid token limits
        )

        if result["ok"]:
            messages = result["messages"]

            for message in messages:
                # Skip messages without text (like file uploads)
                if "text" not in message:
                    continue

                user_id = message.get("user", "unknown")
                text = message["text"]

                # Try to get the username for better context
                try:
                    user_info = await slack_app.client.users_info(user=user_id)
                    if user_info["ok"]:
                        username = (
                            user_info["user"]["real_name"] or user_info["user"]["name"]
                        )
                    else:
                        username = f"User-{user_id}"
                except Exception:
                    username = f"User-{user_id}"

                thread_context.append({"user": username, "text": text})

    except Exception as e:
        logger.error(f"Error gathering thread context: {e}")
        # Return empty context on error - this won't break the flow

    return thread_context


async def send_delayed_reminder(
    user_id: str,
    channel_id: str,
    original_question: str,
    thread_ts: Optional[str] = None,
) -> None:
    """
    Send a delayed reminder if the user hasn't gotten a response.
    """
    # Avoid sending more than one follow-up message per thread in a 10 minute window
    debounced_key = keys.debounced_reminder_key(user_id, thread_ts)
    client = get_redis_client()

    debounced = await client.get(debounced_key)
    if debounced:
        logger.info(
            f"Debounced reminder for user {user_id} and thread {thread_ts}, skipping"
        )
        return
    else:
        await client.set(debounced_key, "1", ex=600)  # 10 minutes

    # Create a more natural follow-up message
    follow_up_messages = [
        f"Hey <@{user_id}>, just wanted to check if my answer about '{original_question[:50]}...' was helpful!",
        f"Hi <@{user_id}>, did my response about '{original_question[:50]}...' answer what you were looking for?",
        f"<@{user_id}>, let me know if you need any clarification on '{original_question[:50]}...' or have follow-up questions!",
    ]

    message = random.choice(follow_up_messages)

    await get_slack_app().client.chat_postMessage(
        channel=channel_id,
        text=message,
        thread_ts=thread_ts,
        mrkdwn=True,
    )


async def generate_rag_response(
    user_id: str, text: str, thread_ts: Optional[str], channel_id: str
) -> str:
    """Generate RAG response for a user question."""

    # Create a progress callback to send status updates
    async def progress_callback(message: str):
        """Send progress status updates to Slack as italicized status messages"""
        try:
            # Format as italic status message: _Thinking..._
            status_text = f"_{message}_"
            # Use Block Kit for proper markdown formatting
            await get_slack_app().client.chat_postMessage(
                channel=channel_id,
                text=status_text,  # Fallback text for notifications
                blocks=[{"type": "markdown", "text": status_text}],
                thread_ts=thread_ts,
            )
            logger.info(f"Sent progress update to user {user_id}: {message}")
        except Exception as e:
            logger.warning(f"Failed to send progress update: {e}")

    # Send immediate acknowledgment BEFORE any heavy operations
    await progress_callback("Thinking...")

    # Now do the expensive operations
    index = get_document_index()
    vectorizer = get_vectorizer()

    # Gather thread context if we have a thread
    thread_context = []
    if thread_ts:
        thread_context = await get_thread_context(channel_id, thread_ts)

    # Process the question using agentic RAG with thread context and progress updates
    # Use thread_ts as session_id for conversation continuity, fallback to channel_id
    session_id = thread_ts or f"channel_{channel_id}"
    return await answer_question(
        index,
        vectorizer,
        text,
        session_id,
        user_id,
        thread_context=thread_context,
        progress_callback=progress_callback,
    )


async def post_slack_message(
    user_id: str, text: str, thread_ts: Optional[str], response: str, channel_id: str
) -> str:
    """Post a message to Slack with feedback buttons."""
    # Truncate message if it exceeds 12,000 characters
    if len(response) > 12000:
        truncated_response = (
            response[: 12000 - len("...(Message too long)")] + "...(Message too long)"
        )
    else:
        truncated_response = response

    # First, store the answer data to get the answer ID
    answer_key = await store_answer_data(user_id, text, response, channel_id, thread_ts)

    # Create blocks with response text and feedback buttons
    # Store the answer ID in the button value for direct lookup
    blocks = [
        {"type": "markdown", "text": truncated_response},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👍 Helpful", "emoji": True},
                    "value": f"thumbs_up:{answer_key}",  # Include answer ID for direct lookup
                    "action_id": "feedback_thumbs_up",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👎 Not Helpful",
                        "emoji": True,
                    },
                    "value": f"thumbs_down:{answer_key}",  # Include answer ID for direct lookup
                    "action_id": "feedback_thumbs_down",
                    "style": "danger",
                },
            ],
        },
    ]

    # Use Block Kit for proper markdown formatting with buttons
    await get_slack_app().client.chat_postMessage(
        channel=channel_id,
        text=truncated_response,  # Fallback text for notifications
        blocks=blocks,
        thread_ts=thread_ts,
    )
    return "posted"


async def store_answer_data(
    user_id: str,
    text: str,
    response: str,
    channel_id: Optional[str],
    thread_ts: Optional[str],
) -> str:
    """Store answer data in Redis for feedback tracking."""
    answer_key = keys.answer_key(user_id, text, thread_ts)
    answer_data = {
        "id": str(ULID()),
        "user_id": user_id,
        "question": text,
        "answer": response,
        "accepted": "",  # should neither be accepted or rejected by default
        "created_at": datetime.now(timezone.utc).timestamp(),
        "updated_at": datetime.now(timezone.utc).timestamp(),
        "thread_ts": thread_ts or "",
        "channel_id": channel_id or "",
    }
    async with get_answer_index() as answer_index:
        await answer_index.load(data=[answer_data], id_field="id", keys=[answer_key])
    return answer_key


async def update_answer_feedback(
    answer_key: str,
    accepted: bool,
) -> str:
    """Update the accepted field for an answer based on user feedback."""
    logger.info(f"Updating feedback - answer_key: {answer_key}, accepted: {accepted}")

    async with get_redis_client() as redis_client:
        # Get the existing answer data directly using the answer_key
        # The answer_key is the full Redis key, so we can fetch it directly
        accepted_val = str(accepted).lower()
        await redis_client.json().set(answer_key, "$.accepted", accepted_val)
        await redis_client.json().set(
            answer_key, "$.updated_at", datetime.now(timezone.utc).timestamp()
        )

        updated = await redis_client.json().get(answer_key)

        if updated["accepted"] != accepted_val:
            logger.error(f"Failed to update answer feedback for {answer_key}")
            raise RuntimeError(
                f"Failed to update answer feedback for {answer_key}. Expected 'accepted' to be '{accepted_val}', but it was not updated."
            )


async def schedule_reminder(
    user_id: str, text: str, thread_ts: Optional[str], channel_id: str
) -> str:
    """Schedule a reminder for a user question."""
    # Don't schedule reminders for brief satisfied responses
    if is_brief_satisfied_response(text):
        logger.info(f"Skipping reminder for brief satisfied response: {text}")
        return "skipped_brief_response"

    # Don't schedule reminders for simple questions like "what's the weather"
    simple_patterns = [
        "what's the weather",
        "who won",
        "when did",
        "what time",
        "what year",
        "how old",
        "where is",
        "what is the capital",
    ]
    text_lower = text.lower()
    if any(pattern in text_lower for pattern in simple_patterns):
        logger.info(f"Skipping reminder for simple factual question: {text}")
        return "skipped_simple_question"

    reminder_key = keys.debounced_reminder_key(user_id, thread_ts)

    return reminder_key


async def post_error_message(
    user_id: str,
    text: str,
    thread_ts: Optional[str],
    error_msg: str,
    channel_id: str,
    retry_attempts: int,
) -> str:
    """Post an error message to Slack."""
    error_text = f"Sorry <@{user_id}>, I encountered an error after {retry_attempts} attempts: {error_msg}"

    # Truncate error message if it exceeds 12,000 characters
    if len(error_text) > 12000:
        truncated_error_text = (
            error_text[: 12000 - len("...(Message too long)")] + "...(Message too long)"
        )
    else:
        truncated_error_text = error_text

    # Use Block Kit for proper markdown formatting
    await get_slack_app().client.chat_postMessage(
        channel=channel_id,
        text=truncated_error_text,  # Fallback text for notifications
        blocks=[{"type": "markdown", "text": truncated_error_text}],
        thread_ts=thread_ts,
    )
    return "error_posted"


async def process_slack_question_with_retry(
    user_id: str,
    text: str,
    channel_id: str,
    thread_ts: Optional[str] = None,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=2)),
) -> None:
    """
    Enhanced task with reentrant side effects for processing RAG questions.
    Each side effect is idempotent, allowing safe retries without duplication.
    """
    try:
        # Log retry attempts
        if retry.attempt > 1:
            logger.info(f"Retry attempt {retry.attempt} for user {user_id}")

        rag_response = await generate_rag_response(user_id, text, thread_ts, channel_id)
        logger.info(f"RAG response ready for user {user_id}")

        await post_slack_message(user_id, text, thread_ts, rag_response, channel_id)
        logger.info(f"Slack message processed for user {user_id}")

        logger.info(f"Successfully processed question for user {user_id}")

    except Exception as e:
        logger.error(f"Error processing question (attempt {retry.attempt}): {e}")

        # On final failure, notify user and schedule reminder
        if (
            retry.attempt is not None
            and retry.attempts is not None
            and retry.attempt >= retry.attempts
        ):
            # Capture the exception for use in the error message
            error_message = str(e)

            try:
                # Side Effect 5: Post error message
                await post_error_message(
                    user_id, text, thread_ts, error_message, channel_id, retry.attempts
                )
                logger.info(f"Error message processed for user {user_id}")
            except Exception as post_error:
                logger.error(f"Failed to post final error message: {post_error}")

        # Re-raise to trigger retry
        raise e


# Thread awareness functions


async def track_thread_participation(
    channel_id: str, thread_ts: str, participated: bool = True
) -> None:
    """Track Agent's participation in a thread."""
    client = get_redis_client()
    participation_key = keys.thread_participation_key(channel_id, thread_ts)
    activity_key = keys.thread_activity_key(channel_id, thread_ts)

    if participated:
        # Mark thread as participated and update activity timestamp

        # Store participation for 1 hour to prevent re-engaging in same thread too frequently
        await client.set(participation_key, "1", ex=3600)  # 1 hour expiry
        await client.set(activity_key, datetime.now(timezone.utc).timestamp(), ex=3600)
        logger.info(f"Tracked participation in thread {channel_id}:{thread_ts}")


async def check_thread_participation(channel_id: str, thread_ts: str) -> bool:
    """Check if Agent has participated in this thread."""
    client = get_redis_client()
    participation_key = keys.thread_participation_key(channel_id, thread_ts)

    result = await client.get(participation_key)
    return bool(result)


async def check_recent_activity(
    channel_id: str, thread_ts: str, timeout_minutes: int = 30
) -> bool:
    """Check if Agent was recently active in this thread."""
    client = get_redis_client()
    activity_key = keys.thread_activity_key(channel_id, thread_ts)

    timestamp_str = await client.get(activity_key)
    if not timestamp_str:
        return False

    try:
        last_activity = datetime.fromtimestamp(float(timestamp_str), timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        return last_activity > cutoff
    except (ValueError, TypeError):
        return False


async def check_rate_limit(
    channel_id: str, thread_ts: str, max_responses: int = 3
) -> bool:
    """Check if we've hit the rate limit for responses in this thread."""
    client = get_redis_client()
    rate_limit_key = keys.thread_rate_limit_key(channel_id, thread_ts)

    # Use Redis to track response count in the last hour
    current_count = await client.get(rate_limit_key)
    if current_count and int(current_count) >= max_responses:
        logger.info(f"Rate limit reached for thread {channel_id}:{thread_ts}")
        return True

    # Increment counter
    await client.incr(rate_limit_key)
    await client.expire(rate_limit_key, 3600)  # 1 hour expiry
    return False


async def evaluate_bump_context(thread_context: list[dict]) -> bool:
    """Evaluate if a 'bump' should trigger a response based on thread context."""
    if not thread_context:
        return False

    # Look at the last 5 messages for context
    recent_messages = (
        thread_context[-5:] if len(thread_context) >= 5 else thread_context
    )

    # Check for unanswered questions
    for msg in reversed(recent_messages):
        message_text = msg.get("text", "")

        # Look for question indicators
        if "?" in message_text:
            logger.info(f"Bump: Found recent question: {message_text[:50]}")
            return True

        # Look for help-seeking language
        help_indicators = [
            "help",
            "how do",
            "how can",
            "what should",
            "need to",
            "trying to",
        ]
        if any(indicator in message_text.lower() for indicator in help_indicators):
            logger.info(f"Bump: Found help-seeking language: {message_text[:50]}")
            return True

        # Look for technical discussions that might benefit from input
        tech_terms = [
            "redis",
            "vector",
            "cache",
            "database",
            "search",
            "index",
            "performance",
            "scaling",
        ]
        if any(term in message_text.lower() for term in tech_terms):
            logger.info(f"Bump: Found technical discussion: {message_text[:50]}")
            return True

    logger.info("Bump: No clear context for response found")
    return False


async def get_bot_user_id() -> str:
    """Get the bot's user ID from Slack API."""
    slack_app = get_slack_app()
    try:
        auth_result = await slack_app.client.auth_test()
        return auth_result["user_id"]
    except Exception as e:
        logger.error(f"Error getting bot user ID: {e}")
        return ""
