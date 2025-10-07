"""
Auth0 configuration for content management API authentication.
"""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Auth0Settings(BaseSettings):
    """Auth0 configuration settings."""

    domain: Optional[str] = Field(
        default=None, description="Auth0 domain (e.g., your-tenant.auth0.com)"
    )

    audience: Optional[str] = Field(
        default=None, description="Auth0 API audience identifier"
    )

    issuer: Optional[str] = Field(default=None, description="Auth0 issuer URL")

    class Config:
        env_prefix = "AUTH0_"
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields that don't match the defined fields


# Global settings instance
auth0_settings = Auth0Settings()


def get_auth0_domain() -> Optional[str]:
    """Get Auth0 domain from environment or settings."""
    return auth0_settings.domain or os.getenv("AUTH0_DOMAIN")


def get_auth0_audience() -> Optional[str]:
    """Get Auth0 audience from environment or settings."""
    return auth0_settings.audience or os.getenv("AUTH0_AUDIENCE")


def get_auth0_issuer() -> Optional[str]:
    """Get Auth0 issuer from environment or settings."""
    if auth0_settings.issuer:
        return auth0_settings.issuer

    domain = get_auth0_domain()
    if domain:
        return f"https://{domain}/"

    return None
