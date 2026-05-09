"""Gmail provider — direct Google API calls."""

import base64
import email.mime.text
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..auth.google_oauth import get_google_token
from .base import CalendarEvent, DraftResult, Email, EmailProvider, EventResult

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GmailProvider(EmailProvider):
    """Gmail + Google Calendar provider using REST API directly."""

    async def _get_client(self) -> tuple[httpx.AsyncClient, dict]:
        token = await get_google_token()
        if not token:
            raise RuntimeError("Google not authenticated — connect via Vicsia Connexions page")
        headers = {"Authorization": f"Bearer {token}"}
        return httpx.AsyncClient(timeout=15), headers

    async def search_emails(self, query: str, max_results: int = 10) -> list[Email]:
        client, headers = await self._get_client()
        async with client:
            # Search for message IDs
            params = {"q": query, "maxResults": max_results}
            logger.info("[gmail] GET %s/messages params=%s", GMAIL_API, params)
            resp = await client.get(
                f"{GMAIL_API}/messages",
                params=params,
                headers=headers,
            )
            logger.info("[gmail] ← status=%d", resp.status_code)
            resp.raise_for_status()
            messages = resp.json().get("messages", [])
            logger.info("[gmail] messages_found=%d", len(messages))

            results = []
            for msg_ref in messages[:max_results]:
                # Fetch each message metadata
                msg_resp = await client.get(
                    f"{GMAIL_API}/messages/{msg_ref['id']}",
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                    headers=headers,
                )
                if msg_resp.status_code != 200:
                    continue
                msg_data = msg_resp.json()
                results.append(_parse_email_metadata(msg_data))

            return results

    async def read_email(self, email_id: str) -> Email:
        client, headers = await self._get_client()
        async with client:
            resp = await client.get(
                f"{GMAIL_API}/messages/{email_id}",
                params={"format": "full"},
                headers=headers,
            )
            resp.raise_for_status()
            return _parse_email_full(resp.json())

    async def create_draft(self, to: str, subject: str, body: str, reply_to: str = "") -> DraftResult:
        client, headers = await self._get_client()
        async with client:
            # Build RFC 2822 message
            mime = email.mime.text.MIMEText(body, "plain", "utf-8")
            mime["To"] = to
            mime["Subject"] = subject
            if reply_to:
                mime["In-Reply-To"] = reply_to
                mime["References"] = reply_to

            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

            draft_body: dict = {"message": {"raw": raw}}
            if reply_to:
                draft_body["message"]["threadId"] = reply_to

            resp = await client.post(
                f"{GMAIL_API}/drafts",
                json=draft_body,
                headers=headers,
            )
            resp.raise_for_status()
            draft_id = resp.json().get("id", "")
            return DraftResult(id=draft_id)

    async def list_events(self, days: int = 7) -> list[CalendarEvent]:
        client, headers = await self._get_client()
        async with client:
            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days)).isoformat()

            resp = await client.get(
                f"{CALENDAR_API}/calendars/primary/events",
                params={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime"},
                headers=headers,
            )
            resp.raise_for_status()

            events = []
            for item in resp.json().get("items", []):
                start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date", ""))
                end = item.get("end", {}).get("dateTime", item.get("end", {}).get("date", ""))
                events.append(
                    CalendarEvent(
                        id=item.get("id", ""),
                        title=item.get("summary", ""),
                        start=start,
                        end=end,
                        location=item.get("location", ""),
                        description=item.get("description", ""),
                        attendees=[a.get("email", "") for a in item.get("attendees", [])],
                    )
                )
            return events

    async def create_event(self, title: str, start: str, end: str, description: str = "") -> EventResult:
        client, headers = await self._get_client()
        async with client:
            event_body = {
                "summary": title,
                "start": {"dateTime": start},
                "end": {"dateTime": end},
            }
            if description:
                event_body["description"] = description

            resp = await client.post(
                f"{CALENDAR_API}/calendars/primary/events",
                json=event_body,
                headers=headers,
            )
            resp.raise_for_status()
            return EventResult(id=resp.json().get("id", ""))


def _get_header(msg_data: dict, name: str) -> str:
    for h in msg_data.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_email_metadata(msg_data: dict) -> Email:
    return Email(
        id=msg_data.get("id", ""),
        subject=_get_header(msg_data, "Subject"),
        sender=_get_header(msg_data, "From"),
        date=_get_header(msg_data, "Date"),
        snippet=msg_data.get("snippet", ""),
    )


def _parse_email_full(msg_data: dict) -> Email:
    em = _parse_email_metadata(msg_data)

    # Extract body from payload
    payload = msg_data.get("payload", {})
    body = _extract_body(payload)
    em.body = body or em.snippet
    return em


def _extract_body(payload: dict) -> str:
    """Extract text body from Gmail payload (handles multipart)."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            body = _extract_body(part)
            if body:
                return body

    return ""
