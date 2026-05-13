"""Google OAuth callback server for vicsia-gmail-mcp.

Handles the OAuth2 PKCE flow:
1. User clicks "Connect" → opens Google consent URL in browser
2. Google redirects to localhost:8000/oauth2callback with auth code
3. This server exchanges the code for tokens and stores them
4. Shows a branded Vicsia success page

Usage:
    from vicsia_gmail_mcp.auth.google_callback import start_google_auth
    start_google_auth()  # Opens browser, waits for callback
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .callback_page import error_page, success_page

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost:8000/oauth2callback"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/calendar"

CREDENTIALS_DIR = Path.home() / ".google_workspace_mcp" / "credentials"


def start_google_auth(client_id: str = "", client_secret: str = "") -> bool:
    """Start Google OAuth flow: open browser, wait for callback.

    Returns True if authentication succeeded.
    """
    client_id = client_id or os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = client_secret or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.error("Missing GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET")
        return False

    # PKCE: generate code verifier + challenge
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = hashlib.sha256(code_verifier.encode()).digest()
    import base64

    code_challenge_b64 = base64.urlsafe_b64encode(code_challenge).rstrip(b"=").decode()

    # Build auth URL
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge_b64,
        "code_challenge_method": "S256",
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    # Start callback server in a thread
    result = {"success": False}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != "/oauth2callback":
                self.send_response(404)
                self.end_headers()
                return

            query = parse_qs(parsed.query)

            # Verify state
            if query.get("state", [None])[0] != state:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(error_page("State mismatch — possible CSRF").encode())
                return

            # Check for error
            if "error" in query:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(error_page(query["error"][0]).encode())
                return

            code = query.get("code", [None])[0]
            if not code:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(error_page("No authorization code received").encode())
                return

            # Exchange code for tokens
            try:
                resp = httpx.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code": code,
                        "redirect_uri": REDIRECT_URI,
                        "code_verifier": code_verifier,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                token_data = resp.json()
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(error_page(f"Token exchange failed: {e}").encode())
                return

            # Get user email
            account = ""
            try:
                userinfo = httpx.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                    timeout=5,
                ).json()
                account = userinfo.get("email", "")
            except Exception:
                pass

            # Store credentials (same format as workspace-mcp)
            _store_credentials(token_data, account, client_id, client_secret)
            result["success"] = True

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(success_page(account, "Gmail").encode())

            # Shutdown server after response
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, format, *args):
            pass  # Suppress HTTP server logs

    server = HTTPServer(("127.0.0.1", 8000), CallbackHandler)

    # Open browser
    logger.info("Opening Google auth page in browser...")
    webbrowser.open(auth_url)

    # Wait for callback (blocking, with timeout)
    server.timeout = 120
    server.handle_request()  # Handle one request then stop

    try:
        server.server_close()
    except Exception:
        pass

    return result["success"]


def _store_credentials(token_data: dict, account: str, client_id: str, client_secret: str) -> None:
    """Store Google credentials in workspace-mcp format."""
    from datetime import datetime, timedelta, timezone

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{account}.json" if account else "default.json"
    creds = {
        "token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "token_uri": GOOGLE_TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES.split(),
        "expiry": (datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat(),
    }

    creds_file = CREDENTIALS_DIR / filename
    creds_file.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    creds_file.chmod(0o600)
    logger.info("Google credentials stored: %s", creds_file)
