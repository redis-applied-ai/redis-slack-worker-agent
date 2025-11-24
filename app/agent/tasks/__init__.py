"""
Agent tasks package for the applied-ai-agent.

This package contains all agent-specific task modules.
"""

# Import all task functions for easy access
from .slack_tasks import (
    check_rate_limit,
    check_recent_activity,
    check_thread_participation,
    evaluate_bump_context,
    generate_rag_response,
    get_bot_user_id,
    get_thread_context,
    post_error_message,
    post_slack_message,
    process_slack_question_with_retry,
    schedule_reminder,
    send_delayed_reminder,
    store_answer_data,
    track_thread_participation,
    update_answer_feedback,
)

# Note: Task registration has been moved to app.worker.task_registration
# This module now only contains the task function definitions


__all__ = [
    # Slack tasks
    "process_slack_question_with_retry",
    "send_delayed_reminder",
    "update_answer_feedback",
    "generate_rag_response",
    "post_slack_message",
    "store_answer_data",
    "schedule_reminder",
    "post_error_message",
    "get_thread_context",
    "track_thread_participation",
    "check_thread_participation",
    "check_recent_activity",
    "check_rate_limit",
    "evaluate_bump_context",
    "get_bot_user_id",
]
