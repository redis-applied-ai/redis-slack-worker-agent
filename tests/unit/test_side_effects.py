"""Test enhanced side effect management with automatic key generation."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.tasks.side_effects import FUNCTION_NAME, clear_side_effects, side_effect
from app.utilities import keys
from settings import SideEffectSettings


class TestSideEffectAutoKeyGeneration:
    """Test automatic key generation from function arguments."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_auto_key_generation_from_args(self, mock_get_redis_client):
        """Test that keys are automatically generated from function name and arguments."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect()  # Default policy is "auto"
        async def test_function(user_id: str, data: dict):
            return f"result-{user_id}"

        # Call with specific arguments
        result = await test_function("user123", {"key": "value"})
        assert result == "result-user123"

        # Verify the key was auto-generated and completion was marked
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args[0]
        completion_key = call_args[0]

        # Key should contain function name and be deterministic
        assert "test_function:" in completion_key
        assert completion_key.startswith("side_effect:completed:")

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_same_args_same_key(self, mock_get_redis_client):
        """Test that same arguments produce the same key (idempotent)."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis

        call_count = 0

        def mock_get_side_effect(key):
            nonlocal call_count
            if call_count == 0:
                call_count += 1
                return None  # First call - not completed
            else:
                return "1"  # Second call - already completed

        mock_redis.get.side_effect = mock_get_side_effect
        mock_redis.set = AsyncMock()

        execution_count = 0

        @side_effect()
        async def test_function(user_id: str, count: int):
            nonlocal execution_count
            execution_count += 1
            return f"result-{execution_count}"

        # First call
        result1 = await test_function("user123", 42)
        assert result1 == "result-1"
        assert execution_count == 1

        # Second call with same args
        result2 = await test_function("user123", 42)
        assert result2 is None  # Skipped execution
        assert execution_count == 1  # Should not increment

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_different_args_different_keys(self, mock_get_redis_client):
        """Test that different arguments produce different keys."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        execution_count = 0

        @side_effect()
        async def test_function(user_id: str):
            nonlocal execution_count
            execution_count += 1
            return f"result-{execution_count}"

        # Call with different arguments
        result1 = await test_function("user1")
        result2 = await test_function("user2")

        assert result1 == "result-1"
        assert result2 == "result-2"
        assert execution_count == 2  # Both should execute


class TestSideEffectKeyPolicies:
    """Test different key generation policies."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_manual_key_policy(self, mock_get_redis_client):
        """Test manual key policy."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect(key="custom-key")
        async def test_function(arg1, arg2):
            return "result"

        await test_function("any", "args")

        # Should use the exact key provided
        expected_completion_key = keys.side_effect_completed_key("custom-key")
        mock_redis.set.assert_called_with(expected_completion_key, "1", ex=3600)

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_function_name_policy(self, mock_get_redis_client):
        """Test function_name key policy (singleton)."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis

        call_count = 0

        def mock_get_side_effect(key):
            nonlocal call_count
            if call_count == 0:
                call_count += 1
                return None  # First call - not completed
            else:
                return "1"  # Subsequent calls - already completed

        mock_redis.get.side_effect = mock_get_side_effect
        mock_redis.set = AsyncMock()

        execution_count = 0

        @side_effect(key_policy=FUNCTION_NAME)
        async def singleton_function(different, args, each, time):
            nonlocal execution_count
            execution_count += 1
            return f"result-{execution_count}"

        # Multiple calls with different args should all use same key
        result1 = await singleton_function("a", "b", "c", "d")
        result2 = await singleton_function("x", "y", "z", "w")

        assert result1 == "result-1"
        assert result2 is None  # Skipped due to same key
        assert execution_count == 1

    def test_policy_validation(self):
        """Test that key and key_policy combinations are validated."""
        # Cannot specify both key and key_policy
        with pytest.raises(
            ValueError, match="Cannot specify both 'key' and 'key_policy'"
        ):
            side_effect(key="test", key_policy=FUNCTION_NAME)


class TestSideEffectTTLHandling:
    """Test TTL (Time To Live) behavior."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_default_ttl(self, mock_get_redis_client):
        """Test default TTL from settings."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect()  # Uses default TTL
        async def test_function():
            return "result"

        await test_function()

        # Should use default TTL (1 hour = 3600 seconds)
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 3600

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_custom_ttl(self, mock_get_redis_client):
        """Test custom TTL."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect(ttl=timedelta(hours=2))
        async def test_function():
            return "result"

        await test_function()

        # Should use custom TTL (2 hours = 7200 seconds)
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 7200

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_persist_forever_none_ttl(self, mock_get_redis_client):
        """Test that ttl=None persists forever."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect(ttl=None)
        async def test_function():
            return "result"

        await test_function()

        # Should set without expiration
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert len(call_args[0]) == 2  # key, value
        assert "ex" not in call_args[1]  # No expiration

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_persist_forever_zero_ttl(self, mock_get_redis_client):
        """Test that ttl=timedelta(0) persists forever."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect(ttl=timedelta(0))
        async def test_function():
            return "result"

        await test_function()

        # Should set without expiration
        mock_redis.set.assert_called()
        call_args = mock_redis.set.call_args
        assert "ex" not in call_args[1]  # No expiration


class TestSideEffectResultStorage:
    """Test result storage and retrieval."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_result_storage_and_retrieval(self, mock_get_redis_client):
        """Test storing and retrieving function results."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis

        # First call - not completed
        mock_redis.get.side_effect = [
            None,  # completion check
        ]
        mock_redis.set = AsyncMock()

        @side_effect(store_result=True)
        async def test_function(value):
            return {"data": value, "computed": True}

        # First execution
        result = await test_function("test")
        assert result == {"data": "test", "computed": True}

        # Verify both completion and result were stored
        assert mock_redis.set.call_count == 2  # completion + result

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_cached_result_retrieval(self, mock_get_redis_client):
        """Test retrieving cached results."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis

        cached_result = {"cached": "data", "from": "redis"}
        mock_redis.get.side_effect = [
            "1",  # Already completed
            json.dumps(cached_result),  # Stored result
        ]

        execution_count = 0

        @side_effect(store_result=True)
        async def test_function(value):
            nonlocal execution_count
            execution_count += 1
            return "should not execute"

        # Should return cached result without executing
        result = await test_function("test")
        assert result == cached_result
        assert execution_count == 0


class TestManualClearing:
    """Test manual clearing of side effects."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_clear_via_environment_variable(self, mock_get_redis_client):
        """Test clearing side effects via environment variable."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.delete = AsyncMock()

        # Mock settings with clear request
        settings = SideEffectSettings(clear_side_effects="test_function")

        @side_effect(settings=settings)
        async def test_function(arg):
            return "result"

        await test_function("value")

        # Should have called delete to clear the side effect
        mock_redis.delete.assert_called()

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_clear_side_effects_function(self, mock_get_redis_client):
        """Test the clear_side_effects utility function."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis

        # Mock scan_iter to return some keys
        async def mock_scan_iter(match):
            keys = [
                "side_effect:completed:test_function:hash1",
                "side_effect:result:test_function:hash1",
                "side_effect:completed:test_function:hash2",
            ]
            for key in keys:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete = AsyncMock(return_value=3)

        # Clear all side effects
        deleted_count = await clear_side_effects("all")

        assert deleted_count == 3
        mock_redis.delete.assert_called_once()


class TestSideEffectFailureHandling:
    """Test failure handling."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_failure_not_marked_complete(self, mock_get_redis_client):
        """Test that failed operations are not marked as completed."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect()
        async def failing_function():
            raise Exception("Operation failed")

        with pytest.raises(Exception, match="Operation failed"):
            await failing_function()

        # Should not mark as completed when operation fails
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_function_metadata_preserved(self, mock_get_redis_client):
        """Test that decorator preserves function metadata."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect()
        async def test_function():
            """Test function docstring."""
            return "result"

        # Check that function metadata is preserved
        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test function docstring."


class TestReentrantTaskPattern:
    """Test the reentrant task pattern using enhanced side effects."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_task_with_auto_keys(self, mock_get_redis_client):
        """Test a task using automatic key generation."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        execution_log = []

        @side_effect()
        async def step1(task_id: str, data: dict):
            execution_log.append(f"step1-{task_id}")
            return f"step1-result-{task_id}"

        @side_effect()
        async def step2(task_id: str, data: dict):
            execution_log.append(f"step2-{task_id}")
            return f"step2-result-{task_id}"

        # Execute a task with multiple steps
        task_id = "task123"
        data = {"input": "test"}

        result1 = await step1(task_id, data)
        result2 = await step2(task_id, data)

        assert result1 == "step1-result-task123"
        assert result2 == "step2-result-task123"
        assert execution_log == ["step1-task123", "step2-task123"]


class TestDecoratorSyntax:
    """Test that side_effect supports both @side_effect and @side_effect() syntax."""

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_bare_decorator_syntax(self, mock_get_redis_client):
        """Test @side_effect syntax (without parentheses)."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        call_count = 0

        @side_effect
        async def test_function_bare(value):
            nonlocal call_count
            call_count += 1
            return f"result-{value}"

        # Use unique value for this test
        unique_value = f"test-bare-{hash('test_bare_decorator_syntax')}"

        # First call should execute
        result1 = await test_function_bare(unique_value)
        assert result1 == f"result-{unique_value}"
        assert call_count == 1

        # Second call should be cached - Mock Redis to return completed
        mock_redis.get.return_value = "1"
        result2 = await test_function_bare(unique_value)
        assert result2 is None  # No result storage by default
        assert call_count == 1  # Should not execute again

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_parentheses_decorator_syntax(self, mock_get_redis_client):
        """Test @side_effect() syntax (with parentheses)."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        call_count = 0

        @side_effect()
        async def test_function_parens(value):
            nonlocal call_count
            call_count += 1
            return f"result-{value}"

        # Use unique value for this test
        unique_value = f"test-parens-{hash('test_parentheses_decorator_syntax')}"

        # First call should execute
        result1 = await test_function_parens(unique_value)
        assert result1 == f"result-{unique_value}"
        assert call_count == 1

        # Second call should be cached - Mock Redis to return completed
        mock_redis.get.return_value = "1"
        result2 = await test_function_parens(unique_value)
        assert result2 is None  # No result storage by default
        assert call_count == 1  # Should not execute again

    @pytest.mark.asyncio
    @patch("app.agent.tasks.side_effects.get_redis_client")
    async def test_both_syntaxes_equivalent(self, mock_get_redis_client):
        """Test that both syntaxes produce equivalent behavior."""
        mock_redis = AsyncMock()
        mock_get_redis_client.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        @side_effect
        async def bare_syntax(value):
            return f"bare-{value}"

        @side_effect()
        async def parentheses_syntax(value):
            return f"parentheses-{value}"

        # Use unique values to avoid Redis collisions
        bare_value = (
            f"test-equivalent-bare-{hash('test_both_syntaxes_equivalent_bare')}"
        )
        parens_value = (
            f"test-equivalent-parens-{hash('test_both_syntaxes_equivalent_parens')}"
        )

        # Both should work the same way
        result1 = await bare_syntax(bare_value)
        result2 = await parentheses_syntax(parens_value)

        assert result1 == f"bare-{bare_value}"
        assert result2 == f"parentheses-{parens_value}"

        # Both should cache subsequent calls - Mock Redis to return completed
        mock_redis.get.return_value = "1"
        cached1 = await bare_syntax(bare_value)
        cached2 = await parentheses_syntax(parens_value)

        assert cached1 is None
        assert cached2 is None
