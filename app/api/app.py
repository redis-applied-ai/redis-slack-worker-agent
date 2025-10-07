"""
Legacy app.py - This file is deprecated and will be removed.

The new API structure is now in app/api/main.py with proper router organization.
This file is kept temporarily for backward compatibility.
"""

# Re-export the new app for backward compatibility
from .main import app

# Keep the app variable for backward compatibility
__all__ = ["app"]
