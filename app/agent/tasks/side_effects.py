"""Side effect management for reentrant task execution."""

import functools
import inspect
import json
import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable, Optional, TypeVar, Union, cast, overload

from app.utilities import keys
from app.utilities.database import get_redis_client
from app.utilities.util import stable_hash
from settings import SideEffectSettings

logger = logging.getLogger(__name__)


# Key policy flags - can be combined with bitwise OR
FUNCTION_SOURCE = 1  # Include function source code hash
FUNCTION_NAME = 2  # Include function name
INPUTS = 4  # Include function inputs (args/kwargs)

# Default key policy
DEFAULT_KEY_POLICY = FUNCTION_SOURCE | FUNCTION_NAME | INPUTS

# Sentinel value to distinguish between "not specified" and "explicitly None"
_UNSPECIFIED = object()

# Type variable for preserving function signature
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


@overload
def side_effect(
    func: F,
) -> F: ...


@overload
def side_effect(
    func: None = None,
    *,
    key: Optional[Union[str, Callable]] = None,
    key_policy: int = DEFAULT_KEY_POLICY,
    ttl: Union[timedelta, None, object] = _UNSPECIFIED,
    store_result: bool = False,
    settings: Optional[SideEffectSettings] = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]: ...


def side_effect(
    func=None,
    *,
    key: Optional[Union[str, Callable]] = None,
    key_policy: int = DEFAULT_KEY_POLICY,
    ttl: Union[timedelta, None, object] = _UNSPECIFIED,
    store_result: bool = False,
    settings: Optional[SideEffectSettings] = None,
):
    """
    Decorator for reentrant task execution with automatic key generation.

    Ensures that decorated functions only execute once per unique key,
    making task execution idempotent and safe for retries.

    Key Generation:
        - Provide `key` (string or callable): Manual key control
        - Use `key_policy` flags: Automatic key generation from function metadata

    Key Policy Flags (can be combined with |):
        - FUNCTION_SOURCE: Include hash of function source code
        - FUNCTION_NAME: Include function name
        - INPUTS: Include function arguments
        - Default: FUNCTION_SOURCE | FUNCTION_NAME | INPUTS

    TTL (Time To Live) Behavior:
        The TTL controls how long the side effect completion marker persists in Redis,
        regardless of whether results are stored. Once TTL expires, the function can
        be executed again.
        - Default: 1 hour (configurable via SIDE_EFFECT_DEFAULT_TTL_HOURS)
        - None: Persist until manually cleared
        - timedelta(0): Same as None - persist forever
        - Custom timedelta: Custom expiration time

    Manual Clearing:
        Set environment variable SIDE_EFFECT_CLEAR_SIDE_EFFECTS to:
        - "all": Clear all side effects
        - "function_name": Clear all side effects for a specific function
        - "function_name:arg_pattern": Clear side effects matching pattern
        - "pattern:*": Clear all side effects matching Redis pattern

    Result Storage:
        - store_result=True: Cache function return values for reuse
        - store_result=False: Only track completion, don't store results

    Examples:
        # Auto key generation with default settings (supports both syntaxes)
        @side_effect
        async def expensive_operation(user_id: str, data: dict):
            # Key auto-generated from function source + name + hash(user_id, data)
            return "result"

        # Same as above, with explicit parentheses
        @side_effect()
        async def expensive_operation_alt(user_id: str, data: dict):
            return "result"

        # Explicit full policy (same as default)
        @side_effect(key_policy=FUNCTION_SOURCE | FUNCTION_NAME | INPUTS)
        async def versioned_operation(data: dict):
            return "result"

        # Manual string key
        @side_effect(key="custom-operation-key")
        async def custom_operation():
            return "result"

        # Manual callable key
        @side_effect(key=lambda func, user_id, action: f"user:{user_id}:action:{action}")
        async def user_action(user_id: str, action: str):
            return "result"

        # Function name only (singleton operation)
        @side_effect(key_policy=FUNCTION_NAME)
        async def singleton_operation():
            return "result"

        # Persist until manually cleared
        @side_effect(ttl=None, store_result=True)
        async def persistent_operation():
            return "cached forever"

        # Custom TTL
        @side_effect(ttl=timedelta(days=1))
        async def daily_operation():
            return "cached for a day"
    """
    if key is not None and key_policy != DEFAULT_KEY_POLICY:
        raise ValueError(
            "Cannot specify both 'key' and 'key_policy' - providing a key implies manual control"
        )

    # Create decorator instance
    decorator = SideEffectDecorator(
        key=key,
        key_policy=key_policy,
        ttl=ttl,
        store_result=store_result,
        settings=settings or SideEffectSettings(),
    )

    if func is None:
        # Called with parentheses: @side_effect(...)
        return cast(
            Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]],
            decorator,
        )
    else:
        # Called without parentheses: @side_effect
        return cast(Callable[..., Awaitable[Any]], decorator(func))


class SideEffectDecorator:
    """Internal decorator implementation."""

    def __init__(
        self,
        key: Optional[Union[str, Callable]] = None,
        key_policy: int = DEFAULT_KEY_POLICY,
        ttl: Union[timedelta, None, object] = _UNSPECIFIED,
        store_result: bool = False,
        settings: Optional[SideEffectSettings] = None,
    ):
        """Initialize side effect decorator."""
        self.key = key
        self.key_policy = key_policy
        self.ttl = ttl
        self.store_result = store_result
        self.settings = settings or SideEffectSettings()

    def _generate_key(self, func: Callable, args: tuple, kwargs: dict) -> str:
        """Generate key based on policy or manual key."""
        if self.key is not None:
            if callable(self.key):
                # Call the key function with func and all arguments
                return self.key(func, *args, **kwargs)
            else:
                # String key
                return self.key

        # Generate key from policy flags
        key_parts = []

        if self.key_policy & FUNCTION_SOURCE:
            # Include hash of function source code
            try:
                source = inspect.getsource(func)
                source_hash = stable_hash(source)
                key_parts.append(f"src:{source_hash}")
            except (OSError, TypeError):
                # Fallback if source is not available
                key_parts.append("src:unavailable")

        if self.key_policy & FUNCTION_NAME:
            key_parts.append(func.__name__)

        if self.key_policy & INPUTS:
            # Generate stable hash from function arguments
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            args_hash = stable_hash(str(bound_args.arguments))
            key_parts.append(f"inputs:{args_hash}")

        if not key_parts:
            raise ValueError("At least one key policy flag must be set")

        return ":".join(key_parts)

    def _get_ttl_seconds(self) -> Optional[int]:
        """Get TTL in seconds, handling various TTL specifications."""
        if self.ttl is _UNSPECIFIED:
            # Use default from settings
            if self.settings.default_ttl_hours is None:
                return None  # Persist forever
            return int(self.settings.default_ttl_hours * 3600)
        elif self.ttl is None or self.ttl == timedelta(0):
            return None  # Persist forever
        else:
            assert isinstance(self.ttl, timedelta)
            return int(self.ttl.total_seconds())

    async def _check_and_clear_if_requested(self, operation_key: str, func_name: str):
        """Check if clearing was requested via environment variable."""
        clear_pattern = self.settings.clear_side_effects
        if not clear_pattern:
            return

        redis_client = get_redis_client()
        should_clear = False

        if clear_pattern == "all":
            should_clear = True
        elif clear_pattern == func_name:
            should_clear = True
        elif clear_pattern.startswith(f"{func_name}:"):
            should_clear = True
        elif clear_pattern.endswith("*"):
            pattern_prefix = clear_pattern[:-1]
            if operation_key.startswith(pattern_prefix):
                should_clear = True

        if should_clear:
            completion_key = keys.side_effect_completed_key(operation_key)
            result_key = (
                keys.side_effect_result_key(operation_key)
                if self.store_result
                else None
            )

            await redis_client.delete(completion_key)
            if result_key:
                await redis_client.delete(result_key)

            logger.info(
                f"Cleared side effect due to CLEAR_SIDE_EFFECTS={clear_pattern}: {operation_key}"
            )

    def __call__(self, func: F) -> F:
        """Apply the decorator to a function."""

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate operation key
            operation_key = self._generate_key(func, args, kwargs)

            # Check for manual clearing request
            await self._check_and_clear_if_requested(operation_key, func.__name__)

            redis_client = get_redis_client()
            completion_key = keys.side_effect_completed_key(operation_key)
            result_key = (
                keys.side_effect_result_key(operation_key)
                if self.store_result
                else None
            )
            ttl_seconds = self._get_ttl_seconds()

            # Check if this side effect has already been completed
            already_completed = await redis_client.get(completion_key)

            if already_completed:
                logger.info(f"Side effect already completed, skipping: {operation_key}")
                if self.store_result and result_key:
                    stored_result = await redis_client.get(result_key)
                    if stored_result:
                        try:
                            return json.loads(stored_result)
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(
                                f"Could not deserialize stored result for {operation_key}"
                            )
                # No result storage or couldn't retrieve result
                return None

            # Side effect hasn't been completed yet - execute it
            logger.info(f"Executing fresh side effect: {operation_key}")

            try:
                result_value = await func(*args, **kwargs)

                # Mark as completed
                if ttl_seconds is not None:
                    await redis_client.set(completion_key, "1", ex=ttl_seconds)
                else:
                    await redis_client.set(completion_key, "1")  # No expiration

                # Store result if requested
                if self.store_result and result_key and result_value is not None:
                    try:
                        serialized_result = json.dumps(result_value)
                        if ttl_seconds is not None:
                            await redis_client.set(
                                result_key, serialized_result, ex=ttl_seconds
                            )
                        else:
                            await redis_client.set(result_key, serialized_result)
                    except (TypeError, ValueError) as e:
                        logger.warning(
                            f"Could not serialize result for {operation_key}: {e}"
                        )

                return result_value

            except Exception as e:
                # Don't mark as completed if operation failed
                logger.error(
                    f"Side effect failed, not marking as completed: {operation_key} - {e}"
                )
                raise

        return cast(F, wrapper)


async def clear_side_effects(pattern: str = "all") -> int:
    """
    Manually clear side effects matching a pattern.

    Args:
        pattern: Pattern to match
            - "all": Clear all side effects
            - "function_name": Clear all for specific function
            - "function_name:*": Clear all with function name prefix
            - Redis key pattern with wildcards

    Returns:
        Number of keys cleared
    """
    redis_client = get_redis_client()
    settings = SideEffectSettings()

    if pattern == "all":
        search_pattern = f"{settings.side_effect_prefix}:*"
    elif ":" not in pattern:
        # Function name only
        search_pattern = f"{settings.side_effect_prefix}:*:{pattern}:*"
    else:
        # Custom pattern
        search_pattern = f"{settings.side_effect_prefix}:*{pattern}*"

    keys_to_delete = []
    async for key in redis_client.scan_iter(match=search_pattern):
        keys_to_delete.append(key)

    if keys_to_delete:
        deleted_count = await redis_client.delete(*keys_to_delete)
        logger.info(
            f"Cleared {deleted_count} side effect keys matching pattern: {pattern}"
        )
        return deleted_count
    else:
        logger.info(f"No side effect keys found matching pattern: {pattern}")
        return 0


async def clear_side_effects_for_function(func: Callable) -> int:
    """
    Clear all side effects for a specific function.

    Args:
        func: The decorated function

    Returns:
        Number of keys cleared
    """
    return await clear_side_effects(func.__name__)


# Export key policy constants for easy importing
__all__ = [
    "side_effect",
    "FUNCTION_SOURCE",
    "FUNCTION_NAME",
    "INPUTS",
    "DEFAULT_KEY_POLICY",
    "clear_side_effects",
    "clear_side_effects_for_function",
]
