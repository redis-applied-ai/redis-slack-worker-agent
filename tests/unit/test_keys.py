"""Test key generation functions for Redis operations."""

from app.utilities import keys


class TestKeyGeneration:
    """Test that key generation functions produce expected patterns."""

    def test_question_key(self):
        """Test question key generation without message timestamp."""
        key = keys.question_key("user123", "test question")
        assert key.startswith("question-user123-")
        assert len(key) > len("question-user123-")  # Should have hash
        # Should not contain a timestamp suffix
        assert not key.endswith("-1234567890.123")

    def test_question_key_with_timestamp(self):
        """Test question key generation with message timestamp."""
        message_ts = "1234567890.123"
        key = keys.question_key("user123", "test question", message_ts)
        assert key.startswith("question-user123-")
        assert key.endswith(f"-{message_ts}")
        # Should be longer than the version without timestamp
        key_without_ts = keys.question_key("user123", "test question")
        assert len(key) > len(key_without_ts)

    def test_question_key_timestamp_uniqueness(self):
        """Test that same question with different timestamps produces unique keys."""
        user_id = "test_user"
        question = "same question"
        ts1 = "1234567890.123"
        ts2 = "1234567890.456"

        key1 = keys.question_key(user_id, question, ts1)
        key2 = keys.question_key(user_id, question, ts2)
        key_no_ts = keys.question_key(user_id, question)

        # All keys should be different
        assert key1 != key2
        assert key1 != key_no_ts
        assert key2 != key_no_ts

        # But all should start with the same prefix (user and question hash)
        prefix = f"question-{user_id}-"
        assert key1.startswith(prefix)
        assert key2.startswith(prefix)
        assert key_no_ts.startswith(prefix)

    def test_question_key_none_timestamp(self):
        """Test that None timestamp is handled same as no timestamp."""
        user_id = "test_user"
        question = "test question"

        key_none = keys.question_key(user_id, question, None)
        key_no_param = keys.question_key(user_id, question)

        assert key_none == key_no_param

    def test_answer_key(self):
        """Test answer key generation with and without thread_ts."""
        # Without thread_ts
        key = keys.answer_key("user123", "test question")
        assert key.startswith("answer:user123-")
        assert "thread" not in key

        # With thread_ts
        key_with_thread = keys.answer_key("user123", "test question", "123456.789")
        assert key_with_thread.startswith("answer:user123-")
        assert key_with_thread.endswith("-123456.789")

    def test_side_effect_keys(self):
        """Test side effect key generation."""
        completion_key = keys.side_effect_completed_key("test-operation")
        result_key = keys.side_effect_result_key("test-operation")

        assert completion_key == "side_effect:completed:test-operation"
        assert result_key == "side_effect:result:test-operation"

    def test_task_operation_keys(self):
        """Test task operation key generation."""
        question_hash = "abc123"

        rag_key = keys.rag_response_key(question_hash)
        slack_key = keys.slack_message_key(question_hash)
        store_key = keys.store_answer_key(question_hash)
        reminder_key = keys.schedule_reminder_key(question_hash)
        error_key = keys.error_message_key(question_hash)
        error_reminder_key = keys.error_reminder_key(question_hash)

        assert rag_key == "rag-response:abc123"
        assert slack_key == "slack-msg:abc123"
        assert store_key == "store-answer:abc123"
        assert reminder_key == "schedule-reminder:abc123"
        assert error_key == "error-msg:abc123"
        assert error_reminder_key == "error-reminder:abc123"

    def test_document_key(self):
        """Test document key generation."""
        key = keys.document_key("repo", "example", 5)
        assert key == "rag_doc:repo:example:5"

    def test_debounced_reminder_key(self):
        """Test debounced reminder key generation."""
        # Without thread_ts
        key = keys.debounced_reminder_key("user123")
        assert key == "debounced-reminder-user123"

        # With thread_ts
        key_with_thread = keys.debounced_reminder_key("user123", "123456.789")
        assert key_with_thread == "debounced-reminder-user123-123456.789"

    def test_session_key(self):
        """Test session key generation."""
        # Without thread_ts
        key = keys.session_key("user123")
        assert key == "session-user123"

        # With thread_ts
        key_with_thread = keys.session_key("user123", "123456.789")
        assert key_with_thread == "session-user123-123456.789"


class TestKeyConsistency:
    """Test that keys are consistent and reproducible."""

    def test_same_inputs_produce_same_keys(self):
        """Test that the same inputs always produce the same keys."""
        user_id = "test_user"
        question = "test question"
        message_ts = "1234567890.123"

        # Without timestamp
        key1 = keys.question_key(user_id, question)
        key2 = keys.question_key(user_id, question)
        assert key1 == key2

        # With timestamp
        key3 = keys.question_key(user_id, question, message_ts)
        key4 = keys.question_key(user_id, question, message_ts)
        assert key3 == key4

        # But keys without timestamp should differ from keys with timestamp
        assert key1 != key3

    def test_different_inputs_produce_different_keys(self):
        """Test that different inputs produce different keys."""
        key1 = keys.question_key("user1", "question1")
        key2 = keys.question_key("user2", "question1")
        key3 = keys.question_key("user1", "question2")

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_repeated_questions_different_messages_unique_keys(self):
        """Test that the same question asked in different messages produces unique keys.

        This validates the fix for the issue where asking the same question
        multiple times in a thread resulted in no response due to key collision.
        """
        user_id = "user123"
        question = "What is Redis?"

        # Simulate the same question asked in different Slack messages
        message1_ts = "1751055816.029429"  # First message
        message2_ts = "1751055820.045678"  # Second message
        message3_ts = "1751055825.067890"  # Third message

        key1 = keys.question_key(user_id, question, message1_ts)
        key2 = keys.question_key(user_id, question, message2_ts)
        key3 = keys.question_key(user_id, question, message3_ts)

        # All keys should be unique despite same user and question
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3

        # But they should share the same prefix (user + question hash)
        assert key1.rsplit("-", 1)[0] == key2.rsplit("-", 1)[0]
        assert key2.rsplit("-", 1)[0] == key3.rsplit("-", 1)[0]

        # The suffixes should be the timestamps
        assert key1.endswith(message1_ts)
        assert key2.endswith(message2_ts)
        assert key3.endswith(message3_ts)

    def test_side_effect_key_patterns(self):
        """Test that side effect keys follow expected patterns."""
        operation_key = "test-op-123"

        completed_key = keys.side_effect_completed_key(operation_key)
        result_key = keys.side_effect_result_key(operation_key)

        # Both should start with the same prefix
        assert completed_key.startswith("side_effect:")
        assert result_key.startswith("side_effect:")

        # But have different suffixes
        assert "completed" in completed_key
        assert "result" in result_key
        assert completed_key != result_key
