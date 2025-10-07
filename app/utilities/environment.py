import os
from typing import Optional

from dotenv import load_dotenv


_env_loaded = False


def reload_env() -> None:
    """Force reload environment variables from .env file."""
    global _env_loaded
    load_dotenv(override=True)
    _env_loaded = True


def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable, reloading from .env file if not already loaded."""
    global _env_loaded
    if not _env_loaded:
        reload_env()
    return os.environ.get(key, default)


def get_required_env_var(key: str) -> str:
    """Get required environment variable, reloading from .env file if not already loaded."""
    global _env_loaded
    if not _env_loaded:
        reload_env()
    value = os.environ.get(key)
    if value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def is_local_mode() -> bool:
    """Check if the application is running in local development mode."""
    local_env = get_env_var("LOCAL", "false").lower()
    return local_env in ("true", "1", "yes", "on")
