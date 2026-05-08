"""Microsoft 365 token loader.

Reads tokens from the same location as Vicsia (~/.vicsia/ms365_token.json).
Vicsia handles the OAuth device code flow — this module only reads and refreshes tokens.

Tokens are stored encrypted by Vicsia's crypto module. If the crypto module
is not available (standalone mode), falls back to plaintext tokens.
"""

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

MS365_CLIENT_ID = os.environ.get("MS365_MCP_CLIENT_ID", "084a3e9f-a9f4-43f7-89f9-d229cf97853e")
MS365_AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
MS365_SCOPES = "User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite offline_access"
MS365_TOKEN_PATH = Path.home() / ".vicsia" / "ms365_token.json"


def _decrypt_if_needed(value: str) -> str:
    """Decrypt a value if Vicsia's crypto module is available."""
    if not value or not value.startswith("gAAAAA"):
        return value  # Plaintext
    try:
        from vicsia_email_mcp.auth._crypto_bridge import decrypt

        return decrypt(value)
    except ImportError:
        logger.warning("Crypto module not available — cannot decrypt token")
        return ""


def has_outlook_credentials() -> bool:
    """Check if Outlook credentials exist."""
    return MS365_TOKEN_PATH.exists()


def get_outlook_token() -> str | None:
    """Load and refresh Outlook token if needed.

    Returns a valid access_token or None.
    """
    if not MS365_TOKEN_PATH.exists():
        return None

    try:
        data = json.loads(MS365_TOKEN_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    access_token = _decrypt_if_needed(data.get("access_token", ""))
    refresh_token = _decrypt_if_needed(data.get("refresh_token", ""))

    # Token still valid (60s margin)
    if time.time() < data.get("expires_at", 0) - 60:
        return access_token if access_token else None

    # Try refresh
    if not refresh_token:
        return None

    try:
        req_data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": MS365_CLIENT_ID,
            "refresh_token": refresh_token,
            "scope": MS365_SCOPES,
        }).encode()
        req = urllib.request.Request(
            f"{MS365_AUTHORITY}/token",
            data=req_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read())

        # Store refreshed token (plaintext in standalone, encrypted if Vicsia available)
        _store_token(token_data)
        return token_data["access_token"]
    except Exception as e:
        logger.warning("MS365 token refresh failed: %s", e)
        return access_token if access_token else None


def _store_token(token_data: dict) -> None:
    """Store token data (plaintext — Vicsia re-encrypts on next load)."""
    MS365_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    MS365_TOKEN_PATH.write_text(
        json.dumps({
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "expires_at": time.time() + token_data.get("expires_in", 3600),
        })
    )
