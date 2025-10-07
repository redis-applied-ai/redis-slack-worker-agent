"""
Slack integration endpoints.

This module provides endpoints for Slack event handling and interactive components.
"""

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.api.slack_app import get_handler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slack"])


@router.post("/slack/events")
async def slack_events(request: Request) -> Dict[str, Any]:
    """
    Handle Slack events (mentions, messages, etc.).

    Args:
        request: FastAPI request object containing Slack event data

    Returns:
        Response indicating success or failure
    """
    try:
        # Log the request details for debugging
        content_type = request.headers.get("content-type", "")
        logger.info(f"Received Slack event - Content-Type: {content_type}")

        # Check if this is an interactive payload
        if "application/x-www-form-urlencoded" in content_type:
            logger.info(
                "Detected form-encoded request, redirecting to interactive handler"
            )
            return await slack_interactive(request)

        return await get_handler().handle(request)
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/test-interactive")
async def test_interactive() -> Dict[str, str]:
    """
    Test endpoint to verify interactive endpoint is accessible.

    Returns:
        Status message indicating the endpoint is ready
    """
    return {
        "status": "Interactive endpoint is accessible",
        "message": "Ready to receive Slack interactive payloads",
    }


@router.post("/slack/interactive")
async def slack_interactive(request: Request) -> Dict[str, str]:
    """
    Handle interactive payloads from Slack (button clicks, etc.).

    Args:
        request: FastAPI request object containing interactive payload data

    Returns:
        Response indicating success or failure
    """
    try:
        # Parse the form data from Slack
        form_data = await request.form()
        payload = form_data.get("payload")

        if not payload:
            logger.error("No payload received in interactive request")
            raise HTTPException(status_code=400, detail="No payload")

        # Parse the JSON payload
        payload_data = json.loads(payload)

        logger.info(f"Received interactive payload: {payload_data}")

        # Handle the interactive payload directly
        # Check if this is a block_actions event (button clicks)
        if payload_data.get("type") == "block_actions":
            actions = payload_data.get("actions", [])
            if actions:
                action = actions[0]
                action_id = action.get("action_id")
                value = action.get("value")

                # Extract user and message details
                message = payload_data.get("message", {})

                logger.info(f"Processing action: {action_id}, value: {value}")

                # Route to the appropriate handler
                if action_id in ["feedback_thumbs_up", "feedback_thumbs_down"]:
                    # Import here to avoid circular imports
                    from ..main import handle_feedback_action

                    # Create a mock body for the feedback handler
                    mock_body = {
                        "actions": [action],
                        "user": payload_data.get("user"),
                        "message": message,
                        "channel": payload_data.get("channel"),
                    }

                    # Create a proper mock ack function
                    async def mock_ack():
                        pass

                    # Call the feedback handler directly
                    await handle_feedback_action(
                        ack=mock_ack,  # Proper async ack function
                        body=mock_body,
                        logger=logger,
                    )

                    return {"status": "ok"}

        # If we get here, it's not a block_actions event we can handle
        logger.warning(
            f"Unhandled interactive payload type: {payload_data.get('type')}"
        )
        return {"status": "ok"}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse interactive payload JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error handling Slack interactive: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
