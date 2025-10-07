from app.utilities.util import stable_hash


def question_key(user_id: str, question: str, message_ts: str | None = None) -> str:
    """Generate a unique key for a question, optionally including message timestamp for uniqueness."""
    ts_suffix = f"-{message_ts}" if message_ts else ""
    return f"question-{user_id}-{stable_hash(question)}{ts_suffix}"


def answer_key(user_id: str, question: str, thread_ts: str | None = None) -> str:
    return f"answer:{user_id}-{stable_hash(question)}{'-' + thread_ts if thread_ts else ''}"


def debounced_reminder_key(user_id: str, thread_ts: str | None = None) -> str:
    return f"debounced-reminder-{user_id}{'-' + thread_ts if thread_ts else ''}"


def session_key(user_id: str, thread_ts: str | None = None) -> str:
    return f"session-{user_id}{'-' + thread_ts if thread_ts else ''}"


def document_key(source_type: str, file_stem: str, chunk_index: int) -> str:
    return f"rag_doc:{source_type}:{file_stem}:{chunk_index}"


# Side effect keys for reentrant task execution
def side_effect_completed_key(operation_key: str) -> str:
    """Key to track if a side effect operation has been completed."""
    return f"side_effect:completed:{operation_key}"


def side_effect_result_key(operation_key: str) -> str:
    """Key to store the result of a side effect operation."""
    return f"side_effect:result:{operation_key}"


# Task operation keys
def rag_response_key(question_hash: str) -> str:
    """Key for RAG response generation side effect."""
    return f"rag-response:{question_hash}"


def slack_message_key(question_hash: str) -> str:
    """Key for Slack message posting side effect."""
    return f"slack-msg:{question_hash}"


def store_answer_key(question_hash: str) -> str:
    """Key for answer data storage side effect."""
    return f"store-answer:{question_hash}"


def schedule_reminder_key(question_hash: str) -> str:
    """Key for reminder scheduling side effect."""
    return f"schedule-reminder:{question_hash}"


def error_message_key(question_hash: str) -> str:
    """Key for error message posting side effect."""
    return f"error-msg:{question_hash}"


def error_reminder_key(question_hash: str) -> str:
    """Key for error reminder scheduling side effect."""
    return f"error-reminder:{question_hash}"


# Thread awareness keys
def thread_participation_key(channel_id: str, thread_ts: str) -> str:
    """Key to track Haink's participation in a thread."""
    return f"thread_participation:{channel_id}:{thread_ts}"


def thread_activity_key(channel_id: str, thread_ts: str) -> str:
    """Key to track Haink's last activity timestamp in a thread."""
    return f"thread_activity:{channel_id}:{thread_ts}"


def thread_rate_limit_key(channel_id: str, thread_ts: str) -> str:
    """Key to track response rate limiting per thread."""
    return f"thread_rate_limit:{channel_id}:{thread_ts}"


def intent_classification_cache_key(message_hash: str) -> str:
    """Key to cache intent classification results."""
    return f"intent_cache:{message_hash}"


def feedback_key(user_id: str, thread_ts: str | None = None) -> str:
    """Key for feedback action side effect."""
    return f"feedback:{user_id}{'-' + thread_ts if thread_ts else ''}"
