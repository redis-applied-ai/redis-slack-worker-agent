"""
Integration tests for Slack app event handling setup and behavior.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


class MockDocket:
    """Mock Docket for testing."""

    def __init__(self, *args, **kwargs):
        self.add_calls = []  # Track calls for verification

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def add(self, func, **kwargs):
        """Mock task addition that returns a callable."""

        async def task_callable(**task_kwargs):
            # Store the call for verification
            self.add_calls.append(
                {"func": func, "add_kwargs": kwargs, "task_kwargs": task_kwargs}
            )
            return None  # Simulate successful task scheduling

        return task_callable

    async def workers(self):
        """Mock workers method."""
        return [
            "worker1",
            "worker2",
        ]  # Return non-empty list to indicate healthy task queue


class TestSlackAppSetup:
    """Test that Slack app is configured correctly with proper event handlers."""

    def test_event_handler_mapping(self):
        """Test that event types map to correct handlers."""

        # This tests the static mapping we expect
        _expected_handlers = {
            "app_mention": "handle_app_mentions",
            "message": "handle_message_events",
        }

        # Import the handlers to verify they exist
        from app.api.main import handle_app_mentions, handle_message_events

        # Verify the handlers are callable
        assert callable(handle_app_mentions)
        assert callable(handle_message_events)

        # Test handler signatures match what Slack expects
        import inspect

        mention_sig = inspect.signature(handle_app_mentions)
        dm_sig = inspect.signature(handle_message_events)

        # Slack handlers should accept body, say, ack at minimum
        mention_params = list(mention_sig.parameters.keys())
        dm_params = list(dm_sig.parameters.keys())

        assert "body" in mention_params
        assert "say" in mention_params
        assert "ack" in mention_params

        assert "body" in dm_params
        assert "say" in dm_params
        assert "ack" in dm_params
        assert "logger" in dm_params  # DM handler has logger


class TestEventTypeProcessing:
    """Test that different Slack event types are processed correctly."""

    @pytest.mark.asyncio
    async def test_app_mention_event_processing(self):
        """Test processing of app_mention events."""
        from app.api.main import handle_app_mentions

        # Test various mention scenarios
        test_cases = [
            {
                "name": "simple_mention",
                "body": {
                    "event": {
                        "type": "app_mention",
                        "user": "U123456789",
                        "text": "<@U987654321> Help me",
                        "channel": "C123456789",
                        "ts": "1234567890.123456",
                    }
                },
                "expected_thread_ts": "1234567890.123456",
            },
            {
                "name": "mention_in_thread",
                "body": {
                    "event": {
                        "type": "app_mention",
                        "user": "U123456789",
                        "text": "<@U987654321> Follow up",
                        "channel": "C123456789",
                        "ts": "1234567890.654321",
                        "thread_ts": "1234567890.123456",
                    }
                },
                "expected_thread_ts": "1234567890.123456",
            },
        ]

        for case in test_cases:
            mock_say = AsyncMock()
            mock_ack = AsyncMock()

            with (
                patch("app.api.main.Docket") as mock_docket_class,
                patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
                patch("app.utilities.database.get_redis_client") as mock_redis_client,
            ):
                mock_docket_instance = MockDocket()
                mock_docket_class.return_value.__aenter__.return_value = (
                    mock_docket_instance
                )

                # Mock slack app for immediate acknowledgment
                mock_slack_app = Mock()
                mock_slack_app.client.chat_postMessage = AsyncMock()
                mock_get_slack_app.return_value = mock_slack_app

                # Mock Redis client for track_thread_participation
                mock_redis_client.return_value.set = AsyncMock()

                await handle_app_mentions(case["body"], mock_say, mock_ack)

                # Verify task was scheduled with correct thread_ts
                assert len(mock_docket_instance.add_calls) == 1
                call = mock_docket_instance.add_calls[0]
                assert (
                    call["task_kwargs"]["thread_ts"] == case["expected_thread_ts"]
                ), f"Failed for case: {case['name']}"

    @pytest.mark.asyncio
    async def test_dm_message_event_processing(self):
        """Test processing of message.im events."""
        from app.api.main import handle_dm_messages

        test_cases = [
            {
                "name": "valid_dm",
                "body": {
                    "event": {
                        "type": "message",
                        "channel_type": "im",
                        "user": "U123456789",
                        "text": "Help me with this",
                        "channel": "D123456789",
                        "ts": "1234567890.123456",
                    }
                },
                "should_process": True,
            },
            {
                "name": "channel_message",
                "body": {
                    "event": {
                        "type": "message",
                        "channel_type": "channel",
                        "user": "U123456789",
                        "text": "Channel message",
                        "channel": "C123456789",
                        "ts": "1234567890.123456",
                    }
                },
                "should_process": False,
            },
            {
                "name": "missing_channel_type",
                "body": {
                    "event": {
                        "type": "message",
                        "user": "U123456789",
                        "text": "No channel type",
                        "channel": "D123456789",
                        "ts": "1234567890.123456",
                    }
                },
                "should_process": True,  # Should process since channel starts with 'D'
            },
        ]

        for case in test_cases:
            mock_say = AsyncMock()
            mock_ack = AsyncMock()
            mock_logger = Mock()

            with (
                patch("app.api.main.Docket") as mock_docket_class,
                patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            ):
                mock_docket_instance = MockDocket()
                mock_docket_class.return_value.__aenter__.return_value = (
                    mock_docket_instance
                )

                # Mock slack app for immediate acknowledgment
                mock_slack_app = Mock()
                mock_slack_app.client.chat_postMessage = AsyncMock()
                mock_get_slack_app.return_value = mock_slack_app

                await handle_dm_messages(case["body"], mock_say, mock_ack, mock_logger)

                if case["should_process"]:
                    # Should schedule task and send immediate acknowledgment
                    assert len(mock_docket_instance.add_calls) == 1

                    # Verify thread_ts is message timestamp for DMs
                    call = mock_docket_instance.add_calls[0]
                    expected_ts = case["body"]["event"]["ts"]
                    assert call["task_kwargs"]["thread_ts"] == expected_ts
                else:
                    # Should not schedule task
                    assert len(mock_docket_instance.add_calls) == 0

                # Always acknowledges
                mock_ack.assert_called_once()

                # Reset for next iteration
                mock_ack.reset_mock()


class TestSlackBotBehaviorRequirements:
    """Test compliance with the specific behavior requirements."""

    @pytest.mark.asyncio
    async def test_only_responds_to_mentions_and_dms(self):
        """Comprehensive test ensuring bot only responds to mentions and DMs."""

        # Test scenarios that should NOT trigger responses
        ignored_scenarios = [
            {
                "name": "regular_channel_message",
                "event_type": "message",
                "body": {
                    "event": {
                        "type": "message",
                        "channel_type": "channel",
                        "user": "U123456789",
                        "text": "Just talking in the channel",
                        "channel": "C123456789",
                        "ts": "1234567890.123456",
                    }
                },
            },
            {
                "name": "group_message",
                "event_type": "message",
                "body": {
                    "event": {
                        "type": "message",
                        "channel_type": "group",
                        "user": "U123456789",
                        "text": "Group conversation",
                        "channel": "G123456789",
                        "ts": "1234567890.123456",
                    }
                },
            },
        ]

        # Test scenarios that SHOULD trigger responses
        processed_scenarios = [
            {
                "name": "app_mention",
                "handler": "handle_app_mentions",
                "body": {
                    "event": {
                        "type": "app_mention",
                        "user": "U123456789",
                        "text": "<@U987654321> Help please",
                        "channel": "C123456789",
                        "ts": "1234567890.123456",
                    }
                },
            },
            {
                "name": "direct_message",
                "handler": "handle_dm_messages",
                "body": {
                    "event": {
                        "type": "message",
                        "channel_type": "im",
                        "user": "U123456789",
                        "text": "Direct message to bot",
                        "channel": "D123456789",
                        "ts": "1234567890.123456",
                    }
                },
            },
        ]

        from app.api.main import handle_app_mentions, handle_dm_messages

        # Test ignored scenarios
        for scenario in ignored_scenarios:
            mock_say = AsyncMock()
            mock_ack = AsyncMock()
            mock_logger = Mock()

            with (
                patch("app.api.main.Docket") as mock_docket_class,
                patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            ):
                mock_docket_instance = MockDocket()
                mock_docket_class.return_value.__aenter__.return_value = (
                    mock_docket_instance
                )

                # Mock slack app
                mock_slack_app = Mock()
                mock_slack_app.client.chat_postMessage = AsyncMock()
                mock_get_slack_app.return_value = mock_slack_app

                await handle_dm_messages(
                    scenario["body"], mock_say, mock_ack, mock_logger
                )

                # Should not process these
                mock_say.assert_not_called()
                assert len(mock_docket_instance.add_calls) == 0
                mock_ack.assert_called_once()  # But should acknowledge

        # Test processed scenarios
        for scenario in processed_scenarios:
            mock_say = AsyncMock()
            mock_ack = AsyncMock()
            mock_logger = Mock()

            with (
                patch("app.api.main.Docket") as mock_docket_class,
                patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
                patch("app.utilities.database.get_redis_client") as mock_redis_client,
            ):
                mock_docket_instance = MockDocket()
                mock_docket_class.return_value.__aenter__.return_value = (
                    mock_docket_instance
                )

                # Mock slack app for immediate acknowledgment
                mock_slack_app = Mock()
                mock_slack_app.client.chat_postMessage = AsyncMock()
                mock_get_slack_app.return_value = mock_slack_app

                # Mock Redis client for track_thread_participation
                mock_redis_client.return_value.set = AsyncMock()

                if scenario["handler"] == "handle_app_mentions":
                    await handle_app_mentions(scenario["body"], mock_say, mock_ack)
                    # Note: No immediate chat_postMessage expected - response happens in background task
                else:
                    await handle_dm_messages(
                        scenario["body"], mock_say, mock_ack, mock_logger
                    )
                    # Note: No immediate chat_postMessage expected - response happens in background task

                # Should process these
                assert len(mock_docket_instance.add_calls) == 1
                mock_ack.assert_called_once()

    @pytest.mark.asyncio
    async def test_threading_behavior_compliance(self):
        """Test threading behavior matches requirements exactly."""
        from app.api.main import handle_app_mentions, handle_dm_messages

        mock_say = AsyncMock()
        mock_ack = AsyncMock()
        mock_logger = Mock()

        with (
            patch("app.api.main.Docket") as mock_docket_class,
            patch("app.api.slack_app.get_slack_app") as mock_get_slack_app,
            patch("app.utilities.database.get_redis_client") as mock_redis_client,
        ):
            mock_docket_instance = MockDocket()
            mock_docket_class.return_value.__aenter__.return_value = (
                mock_docket_instance
            )

            # Mock slack app for immediate acknowledgment
            mock_slack_app = Mock()
            mock_slack_app.client.chat_postMessage = AsyncMock()
            mock_get_slack_app.return_value = mock_slack_app

            # Mock Redis client for track_thread_participation
            mock_redis_client.return_value.set = AsyncMock()

            # 1. Mention in channel should create thread using message ts
            channel_mention = {
                "event": {
                    "type": "app_mention",
                    "user": "U123456789",
                    "text": "<@U987654321> Help with X",
                    "channel": "C123456789",
                    "ts": "1234567890.111111",
                }
            }

            await handle_app_mentions(channel_mention, mock_say, mock_ack)
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.111111"
            )  # Creates thread

            # 2. Mention in existing thread should preserve thread_ts
            mock_docket_instance.add_calls.clear()
            thread_mention = {
                "event": {
                    "type": "app_mention",
                    "user": "U123456789",
                    "text": "<@U987654321> Follow up",
                    "channel": "C123456789",
                    "ts": "1234567890.222222",
                    "thread_ts": "1234567890.111111",  # Original thread
                }
            }

            await handle_app_mentions(thread_mention, mock_say, mock_ack)
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.111111"
            )  # Preserves original

            # 3. DM should create threading using message timestamp
            mock_docket_instance.add_calls.clear()
            dm_message = {
                "event": {
                    "type": "message",
                    "channel_type": "im",
                    "user": "U123456789",
                    "text": "DM question",
                    "channel": "D123456789",
                    "ts": "1234567890.333333",
                }
            }

            await handle_dm_messages(dm_message, mock_say, mock_ack, mock_logger)
            assert len(mock_docket_instance.add_calls) == 1
            call = mock_docket_instance.add_calls[0]
            assert (
                call["task_kwargs"]["thread_ts"] == "1234567890.333333"
            )  # Creates thread using message ts


class TestThreadContextGathering:
    """Test thread context gathering functionality."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.slack_tasks.get_slack_app")
    async def test_get_thread_context_success(self, mock_get_slack_app):
        """Test successful thread context gathering."""
        from app.agent.tasks import get_thread_context

        # Mock slack app and client
        mock_slack_app = Mock()
        mock_client = AsyncMock()
        mock_slack_app.client = mock_client
        mock_get_slack_app.return_value = mock_slack_app

        # Mock conversations_replies response
        mock_replies_response = {
            "ok": True,
            "messages": [
                {"user": "U123", "text": "Original question about Redis AI"},
                {"user": "U456", "text": "Follow up question"},
            ],
        }
        mock_client.conversations_replies = AsyncMock(
            return_value=mock_replies_response
        )

        # Mock users_info responses
        async def mock_users_info(user):
            users = {
                "U123": {
                    "ok": True,
                    "user": {"real_name": "Alice Smith", "name": "alice"},
                },
                "U456": {"ok": True, "user": {"real_name": "Bob Jones", "name": "bob"}},
            }
            return users.get(user, {"ok": False})

        mock_client.users_info.side_effect = mock_users_info

        # Execute
        result = await get_thread_context("C123", "1234567890.111111")

        # Verify
        assert len(result) == 2
        assert result[0]["user"] == "Alice Smith"
        assert result[0]["text"] == "Original question about Redis AI"
        assert result[1]["user"] == "Bob Jones"
        assert result[1]["text"] == "Follow up question"

        # Verify API calls
        mock_client.conversations_replies.assert_called_once_with(
            channel="C123", ts="1234567890.111111", limit=50
        )
        assert mock_client.users_info.call_count == 2

    @pytest.mark.asyncio
    @patch("app.agent.tasks.slack_tasks.get_slack_app")
    async def test_get_thread_context_api_error(self, mock_get_slack_app):
        """Test thread context gathering handles API errors gracefully."""
        from app.agent.tasks import get_thread_context

        # Mock slack app and client
        mock_slack_app = Mock()
        mock_client = AsyncMock()
        mock_slack_app.client = mock_client
        mock_get_slack_app.return_value = mock_slack_app

        # Mock API error
        mock_client.conversations_replies = AsyncMock(
            side_effect=Exception("Slack API Error")
        )

        # Execute
        result = await get_thread_context("C123", "1234567890.111111")

        # Should return empty list on error
        assert result == []

    @pytest.mark.asyncio
    @patch("app.agent.tasks.slack_tasks.get_slack_app")
    async def test_get_thread_context_user_lookup_failure(self, mock_get_slack_app):
        """Test thread context gathering handles user lookup failures."""
        from app.agent.tasks import get_thread_context

        # Mock slack app and client
        mock_slack_app = Mock()
        mock_client = AsyncMock()
        mock_slack_app.client = mock_client
        mock_get_slack_app.return_value = mock_slack_app

        # Mock conversations_replies response
        mock_replies_response = {
            "ok": True,
            "messages": [{"user": "U123", "text": "Question from unknown user"}],
        }
        mock_client.conversations_replies = AsyncMock(
            return_value=mock_replies_response
        )

        # Mock users_info failure
        mock_client.users_info = AsyncMock(side_effect=Exception("User lookup failed"))

        # Execute
        result = await get_thread_context("C123", "1234567890.111111")

        # Should use fallback username
        assert len(result) == 1
        assert result[0]["user"] == "User-U123"
        assert result[0]["text"] == "Question from unknown user"
