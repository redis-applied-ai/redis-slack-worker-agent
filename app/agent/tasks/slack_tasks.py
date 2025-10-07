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
    """Track Haink's participation in a thread."""
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
    """Check if Haink has participated in this thread."""
    client = get_redis_client()
    participation_key = keys.thread_participation_key(channel_id, thread_ts)

    result = await client.get(participation_key)
    return bool(result)


async def check_recent_activity(
    channel_id: str, thread_ts: str, timeout_minutes: int = 30
) -> bool:
    """Check if Haink was recently active in this thread."""
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


async def classify_message_intent(
    message_text: str, thread_context: list[dict]
) -> dict:
    """Use GPT-4.1-nano to classify if message is directed at Haink."""
    # Check cache first
    message_hash = hashlib.sha256(message_text.encode()).hexdigest()
    cache_key = keys.intent_classification_cache_key(message_hash)
    client = get_redis_client()

    cached_result = await client.get(cache_key)
    if cached_result:
        try:
            return json.loads(cached_result)
        except json.JSONDecodeError:
            pass

    # Prepare context for classification
    recent_context = thread_context[-3:] if len(thread_context) > 3 else thread_context
    context_str = "\n".join([f"{msg['user']}: {msg['text']}" for msg in recent_context])

    prompt = f"""Analyze if this Slack message is directed at an AI assistant named Haink:

Message: "{message_text}"
Recent context: {context_str}

Return JSON:
{{
    "is_for_ai": boolean,
    "confidence": float (0.0-1.0),
    "intent_type": "question|followup|clarification|feedback|off_topic",
    "reasoning": "brief explanation"
}}"""

    try:
        from app.openai_client import get_instrumented_client

        client_openai = get_instrumented_client()
        response = client_openai.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.1,
        )

        content = response.choices[0].message.content
        if content:
            result = json.loads(content)
            # Cache the result for 1 hour
            await client.set(cache_key, json.dumps(result), ex=3600)
            return result

    except Exception as e:
        logger.error(f"Error in intent classification: {e}")

    # Fallback: conservative classification
    return {
        "is_for_ai": False,
        "confidence": 0.0,
        "intent_type": "off_topic",
        "reasoning": "Classification failed, defaulting to conservative",
    }


async def check_haink_mention_in_thread(channel_id: str, thread_ts: str) -> bool:
    """Check if Haink has been mentioned anywhere in the thread."""
    try:
        slack_app = get_slack_app()
        bot_user_id = await get_bot_user_id()

        result = await slack_app.client.conversations_replies(
            channel=channel_id, ts=thread_ts, limit=50
        )

        if result["ok"]:
            messages = result["messages"]
            for message in messages:
                text = message.get("text", "")
                if f"<@{bot_user_id}>" in text:
                    return True
        return False

    except Exception as e:
        logger.error(f"Error checking mentions in thread: {e}")
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


async def should_respond_to_thread_message(
    channel_id: str, thread_ts: str, user_id: str, message_text: str
) -> bool:
    """Determine if Haink should respond to a non-mention thread message."""

    # Check if we're being rate limited
    if await check_rate_limit(channel_id, thread_ts):
        return False

    # Handle "bump" - empty message with just Haink mention (handled elsewhere)
    # This function should be more conservative and only respond to clear questions

    # Get thread context for analysis
    thread_context = await get_thread_context(channel_id, thread_ts)

    # Only respond if:
    # 1. There's a clear question mark in recent messages
    # 2. OR someone seems to be waiting for technical help/clarification
    # 3. AND we haven't responded to anything similar recently

    # Look for question indicators in the current message
    question_indicators = [
        "?",
        "how",
        "what",
        "why",
        "when",
        "where",
        "which",
        "can you",
        "could you",
        "help",
    ]
    has_question = any(
        indicator in message_text.lower() for indicator in question_indicators
    )

    # Look for technical terms that might need clarification
    tech_terms = [
        "redis",
        "vector",
        "cache",
        "database",
        "ai",
        "ml",
        "search",
        "index",
        "query",
    ]
    has_tech_terms = any(term in message_text.lower() for term in tech_terms)

    # CRITICAL: If someone is @mentioning another user, NEVER butt in
    # Look for @username or @here or @channel patterns
    import re

    bot_user_id = await get_bot_user_id()

    # Check for @mentions that aren't Haink
    at_mention_pattern = r"@\w+|@here|@channel|<@[^>]+>"
    mentions_found = re.findall(at_mention_pattern, message_text)

    # Filter out Haink's own mention
    other_mentions = [m for m in mentions_found if f"<@{bot_user_id}>" not in m]

    if other_mentions:
        logger.info(
            f"BLOCKING response - message has @mentions for others: {other_mentions} in '{message_text[:50]}'"
        )
        return False

    # Also block if the message is clearly directed at someone else contextually
    directed_patterns = [
        r"^@\w+",  # Starts with @username
        r"hey @\w+",
        r"hi @\w+",
        r"@\w+[,:]",  # @username, or @username:
    ]

    for pattern in directed_patterns:
        if re.search(pattern, message_text.lower()):
            logger.info(
                f"BLOCKING response - message directed at someone else: '{message_text[:50]}'"
            )
            return False

    # Be VERY conservative - only respond if there's a clear question AND tech terms
    # AND the AI is very confident it's directed at Haink
    should_respond = has_question and has_tech_terms

    if should_respond:
        # Double-check with AI classification for complex cases
        classification = await classify_message_intent(message_text, thread_context)
        is_for_ai = classification.get("is_for_ai", False)
        confidence = classification.get("confidence", 0.0)

        logger.info(
            f"Thread analysis - Question: {has_question}, Tech: {has_tech_terms}, AI confident: {is_for_ai} ({confidence})"
        )

        # Be much more conservative - require high confidence AND explicit indicators
        if confidence >= 0.8 and is_for_ai:
            # Additional safety check: if message mentions "Haink" but isn't a direct question TO Haink, be careful
            if "haink" in message_text.lower() and not any(
                pattern in message_text.lower()
                for pattern in [
                    "haink can you",
                    "haink could you",
                    "haink help",
                    "haink what",
                    "haink how",
                    "haink why",
                ]
            ):
                logger.info(
                    f"BLOCKING - mentions Haink but doesn't seem directed at him: '{message_text[:50]}'"
                )
                return False
            return True

    logger.info(
        f"Not responding - Question: {has_question}, Tech: {has_tech_terms}, Should: {should_respond}"
    )
    return False
