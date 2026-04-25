"""Google OAuth token loader.

Reads tokens from the same location as workspace-mcp (~/.google_workspace_mcp/credentials/).
Vicsia handles the OAuth flow — this module only reads and refreshes tokens.
"""

import json
import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_DIR = Path.home() / ".google_workspace_mcp" / "credentials"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _find_credentials_file() -> Path | None:
    """Find the first valid credentials JSON file."""
    if not GOOGLE_TOKEN_DIR.exists():
        return None
    for f in GOOGLE_TOKEN_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("access_token") or data.get("refresh_token"):
                return f
        except (json.JSONDecodeError, OSError):
            continue
    return None


def has_google_credentials() -> bool:
    """Check if Google credentials exist."""
    return _find_credentials_file() is not None


async def get_google_token() -> str | None:
    """Load and refresh Google OAuth token if needed.

    Returns a valid access_token or None.
    """
    creds_file = _find_credentials_file()
    if not creds_file:
        return None

    try:
        data = json.loads(creds_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    expiry = data.get("expiry", "")

    # Check if token is still valid (with 60s margin)
    if expiry and access_token:
        try:
            from datetime import datetime, timezone

            exp_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if exp_dt.timestamp() > time.time() + 60:
                return access_token
        except (ValueError, TypeError):
            pass

    # Try refresh
    if not refresh_token:
        logger.warning("No refresh_token in Google credentials")
        return access_token if access_token else None

    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("Missing GOOGLE_OAUTH_CLIENT_ID/SECRET for token refresh")
        return access_token if access_token else None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        # Update credentials file
        data["access_token"] = token_data["access_token"]
        if "refresh_token" in token_data:
            data["refresh_token"] = token_data["refresh_token"]
        if "expires_in" in token_data:
            from datetime import datetime, timedelta, timezone

            data["expiry"] = (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat()

        creds_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return token_data["access_token"]
    except Exception as e:
        logger.warning("Google token refresh failed: %s", e)
        return access_token if access_token else None
