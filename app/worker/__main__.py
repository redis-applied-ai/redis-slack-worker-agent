"""
Entry point for running the worker module with: uv run python -m app.worker
"""

import asyncio
from .worker import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Worker stopped by user")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        raise
