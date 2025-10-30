"""
Docket worker for processing background tasks.
Run with: uv run python -m app.worker
"""

import asyncio
import logging
import os
import sys
import traceback
from datetime import timedelta

from docket import Worker
from dotenv import load_dotenv

from app.utilities.logging_config import ensure_stdout_logging

# Set up logging for the worker
logger = logging.getLogger(__name__)

# Add project root to Python path if needed
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()


async def main():
    """Run the Docket worker."""
    # Ensure logs go to stdout with a sane default
    ensure_stdout_logging()

    redis_url = os.environ.get("REDIS_URL")

    if not redis_url:
        error_msg = "REDIS_URL environment variable not set"
        print(f"❌ {error_msg}")
        logger.error(error_msg)
        return

    logger.debug("Worker Redis connection configured")
    logger.info("Starting Docket worker")
    print("Starting Docket worker")

    # Initialize metrics for the worker
    try:
        from app.utilities.metrics import setup_metrics

        setup_metrics()
        print("✅ Metrics initialized for worker")
        logger.info("Metrics initialized for worker")
    except Exception as e:
        error_msg = f"Failed to initialize metrics: {e}"
        print(f"⚠️  {error_msg}")
        logger.warning(error_msg)

    # Initialize telemetry for the worker
    try:
        from app.utilities.telemetry import setup_telemetry

        setup_telemetry()
        print("✅ Telemetry initialized for worker")
        logger.info("Telemetry initialized for worker")
    except Exception as e:
        error_msg = f"Failed to initialize telemetry: {e}"
        print(f"⚠️  {error_msg}")
        logger.warning(error_msg)

    # Log LLM provider/model at worker startup
    try:
        provider = os.getenv("LLM_PROVIDER", "bedrock").lower()
        if provider == "bedrock":
            model = os.getenv(
                "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"
            )
        else:
            model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1")
        logger.info(f"LLM configured: provider={provider} model={model} (worker)")
        # Also print to stdout to guarantee visibility regardless of logging config
        print(f"LLM configured: provider={provider} model={model} (worker)")
    except Exception as e:
        logger.warning(f"Could not determine LLM provider/model: {e}")

    # Tasks will be registered automatically by Worker.run() from all_tasks

    # Main worker loop with comprehensive error handling
    restart_count = 0
    max_restarts = 10

    while restart_count < max_restarts:
        try:
            print("✅ Worker started, waiting for tasks...")
            print("Press Ctrl+C to stop")
            logger.debug(f"Worker restart count: {restart_count}/{max_restarts}")

            logger.info(f"Worker starting (restart {restart_count}/{max_restarts})")
            logger.info("Worker waiting for tasks...")

            # Start worker
            logger.debug("Starting Worker.run()")
            logger.debug("About to start Worker.run()")

            await Worker.run(
                docket_name="applied-ai-agent",
                url=redis_url,
                concurrency=1,  # Reduced concurrency to prevent resource issues
                redelivery_timeout=timedelta(seconds=60),
                tasks=["app.worker.task_registration:all_tasks"],
            )

            logger.debug("Worker.run() completed normally")
            logger.info("Worker.run() completed normally")
            logger.debug("Restarting worker...")
            logger.info("Restarting worker...")

        except KeyboardInterrupt:
            logger.debug("Worker interrupted by user (Ctrl+C)")
            logger.info("Worker stopped by user interrupt")
            break
        except Exception as e:
            restart_count += 1
            error_msg = f"Worker error (restart {restart_count}/{max_restarts}): {e}"
            print(f"❌ {error_msg}")
            logger.debug(f"Worker error type: {type(e).__name__}")
            logger.debug(f"Worker error args: {e.args}")

            traceback_str = traceback.format_exc()
            logger.debug(f"Worker error traceback: {traceback_str}")

            # Log comprehensive error details for CloudWatch
            logger.error(error_msg)
            logger.error(f"Worker error type: {type(e).__name__}")
            logger.error(f"Worker error args: {e.args}")
            logger.error(f"Worker error traceback: {traceback_str}")

            if restart_count >= max_restarts:
                logger.critical(
                    f"Worker exceeded maximum restart attempts ({max_restarts}). Exiting."
                )
                print(
                    f"💥 Worker exceeded maximum restart attempts ({max_restarts}). Exiting."
                )
                break

            logger.debug(
                f"Restarting worker in 5 seconds... (attempt {restart_count}/{max_restarts})"
            )
            logger.info(
                f"Worker will restart in 5 seconds (attempt {restart_count}/{max_restarts})"
            )
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Worker stopped by user")
        logger.info("Worker stopped by user")
    except Exception as e:
        error_msg = f"Unexpected error in main: {e}"
        print(f"💥 {error_msg}")
        logger.critical(error_msg)
        logger.critical(f"Unexpected error traceback: {traceback.format_exc()}")
        raise
