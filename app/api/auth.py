"""
Ultra-simple Auth0 authentication for FastAPI web interface.
No complex libraries, just basic HTTP requests and session management.
"""

import json
import logging
import os
import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.auth_config import get_auth0_domain
from app.utilities.environment import is_local_mode

# Initialize logger and templates
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

# Auth0 configuration
AUTH0_DOMAIN = get_auth0_domain()
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET")

# Simple in-memory session storage (use Redis in production)
sessions: Dict[str, Dict[str, Any]] = {}


def get_session_id(request: Request) -> str:
    """Get or create session ID from request."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = secrets.token_urlsafe(32)
    return session_id


def get_session(request: Request) -> Optional[Dict[str, Any]]:
    """Get session data from request."""
    session_id = get_session_id(request)
    return sessions.get(session_id)


def set_session(request: Request, session_data: Dict[str, Any]) -> str:
    """Set session data and return session ID."""
    session_id = get_session_id(request)
    sessions[session_id] = session_data
    return session_id


def clear_session(request: Request) -> str:
    """Clear session data and return session ID."""
    session_id = get_session_id(request)
    if session_id in sessions:
        del sessions[session_id]
    return session_id


async def login(request: Request):
    """Start Auth0 login."""
    if not AUTH0_DOMAIN or not AUTH0_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Auth0 not configured")

    # Build callback URL
    base_url = os.getenv("BASE_URL") or f"{request.url.scheme}://{request.url.netloc}"
    callback_url = f"{base_url}/callback"

    # Debug logging
    logger.debug("Processing login request")
    logger.debug(f"Base URL: {base_url}")
    logger.debug(f"Callback URL: {callback_url}")

    # Generate state for security
    state = secrets.token_urlsafe(32)

    # Save state in session
    session_id = get_session_id(request)
    sessions[session_id] = {"state": state, "callback_url": callback_url}

    # Build Auth0 login URL
    params = {
        "response_type": "code",
        "client_id": AUTH0_CLIENT_ID,
        "redirect_uri": callback_url,
        "scope": "openid profile email",
        "state": state,
    }

    auth_url = f"https://{AUTH0_DOMAIN}/authorize?" + urlencode(params)
    logger.debug("Redirecting to Auth0 for authentication")

    # Redirect with session cookie
    response = RedirectResponse(url=auth_url)
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")

    return response


async def callback(request: Request):
    """Handle Auth0 callback."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code:
        raise HTTPException(status_code=400, detail="No code from Auth0")

    # Get session and verify state
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=400, detail="No session")

    session_data = sessions[session_id]
    if session_data.get("state") != state:
        raise HTTPException(status_code=400, detail="Invalid state")

    # Use the same callback URL that was used in the authorization request
    callback_url = session_data.get("callback_url")
    if not callback_url:
        # Fallback to constructing it
        base_url = (
            os.getenv("BASE_URL") or f"{request.url.scheme}://{request.url.netloc}"
        )
        callback_url = f"{base_url}/callback"

    token_data = {
        "grant_type": "authorization_code",
        "client_id": AUTH0_CLIENT_ID,
        "client_secret": AUTH0_CLIENT_SECRET,
        "code": code,
        "redirect_uri": callback_url,
    }

    async with httpx.AsyncClient() as client:
        # Use client_secret in POST data (Client Secret Post method)
        logger.debug("Using Client Secret Post method")

        # Add Content-Type header explicitly
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        # Get tokens using POST data with client_secret
        token_response = await client.post(
            f"https://{AUTH0_DOMAIN}/oauth/token", data=token_data, headers=headers
        )

        logger.debug(f"Token response status: {token_response.status_code}")

        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.status_code}")
            raise HTTPException(
                status_code=500,
                detail=f"Token exchange failed: {token_response.status_code}",
            )

        tokens = token_response.json()

        # Get user info
        user_response = await client.get(
            f"https://{AUTH0_DOMAIN}/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

        if user_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to get user info")

        userinfo = user_response.json()

    # Save user in session
    sessions[session_id] = {"userinfo": userinfo}

    # Redirect to home
    response = RedirectResponse(url="/")
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")

    return response


async def logout(request: Request):
    """Logout user."""
    clear_session(request)

    # Build Auth0 logout URL
    logout_url = (
        f"https://{AUTH0_DOMAIN}/v2/logout?"
        f"returnTo={os.getenv('BASE_URL') or request.base_url}&"
        f"client_id={AUTH0_CLIENT_ID}"
    )

    response = RedirectResponse(url=logout_url)
    response.delete_cookie("session_id")

    return response


async def home(request: Request):
    """Home page."""
    # In local development mode, redirect directly to content management
    if is_local_mode():
        return RedirectResponse(url="/content")
    
    session_data = get_session(request)

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "session": session_data,
            "pretty": json.dumps(session_data, indent=2) if session_data else None,
        },
    )


async def content_page(request: Request):
    """Content management page - requires auth unless in LOCAL mode."""
    # In local development mode, bypass authentication
    if is_local_mode():
        # Create mock session data for local development
        mock_session = {
            "userinfo": {
                "sub": "local_dev_user",
                "email": "local@development.com",
                "name": "Local Development User"
            },
            "access_token": "local_dev_token",
            "local_mode": True
        }
        return templates.TemplateResponse(
            "content.html",
            {
                "request": request,
                "session": mock_session,
                "pretty": json.dumps(mock_session, indent=2),
            },
        )
    
    # Normal authentication flow for production
    session_data = get_session(request)

    if not session_data or not session_data.get("userinfo"):
        return RedirectResponse(url="/login")

    return templates.TemplateResponse(
        "content.html",
        {
            "request": request,
            "session": session_data,
        },
    )


def require_auth(request: Request):
    """Dependency to require authentication."""
    session_data = get_session(request)
    if not session_data or not session_data.get("userinfo"):
        raise HTTPException(status_code=401, detail="Login required")
    return session_data


async def debug_callback_url(request: Request):
    """Debug endpoint for Auth0 setup."""
    base_url = os.getenv("BASE_URL") or f"{request.url.scheme}://{request.url.netloc}"

    return {
        "callback_url": f"{base_url}/callback",
        "auth0_domain": AUTH0_DOMAIN,
        "client_id": AUTH0_CLIENT_ID,
        "note": "Add this callback_url to your Auth0 application settings",
    }
