"""Outlook/MS365 provider — direct Microsoft Graph API calls."""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..auth.ms_token import get_outlook_token
from .base import CalendarEvent, DraftResult, Email, EmailProvider, EventResult

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.microsoft.com/v1.0"


class OutlookProvider(EmailProvider):
    """Outlook / Microsoft 365 provider using Graph API directly."""

    async def _get_client(self) -> tuple[httpx.AsyncClient, dict]:
        token = get_outlook_token()
        if not token:
            raise RuntimeError("Outlook not authenticated — connect via Vicsia Connexions page")
        headers = {"Authorization": f"Bearer {token}"}
        return httpx.AsyncClient(timeout=15), headers

    async def search_emails(self, query: str, max_results: int = 10) -> list[Email]:
        client, headers = await self._get_client()
        async with client:
            # Graph API: $search and $orderby cannot be combined
            params: dict = {
                "$top": max_results,
                "$select": "id,subject,from,receivedDateTime,bodyPreview",
            }
            if query and query.lower() not in ("inbox", "all", "*"):
                params["$search"] = f'"{query}"'
            else:
                params["$orderby"] = "receivedDateTime desc"

            # Scope explicite à Inbox — /me/messages couvre toute la mailbox
            # (drafts, sent, deleted, clutter) et $search aussi malgré la doc MS.
            resp = await client.get(
                f"{GRAPH_API}/me/mailFolders/inbox/messages",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()

            results = []
            for msg in resp.json().get("value", []):
                sender = msg.get("from", {}).get("emailAddress", {})
                results.append(
                    Email(
                        id=msg.get("id", ""),
                        subject=msg.get("subject", ""),
                        sender=f"{sender.get('name', '')} <{sender.get('address', '')}>",
                        date=msg.get("receivedDateTime", ""),
                        snippet=msg.get("bodyPreview", ""),
                    )
                )
            return results

    async def read_email(self, email_id: str) -> Email:
        client, headers = await self._get_client()
        async with client:
            resp = await client.get(
                f"{GRAPH_API}/me/messages/{email_id}",
                params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview"},
                headers=headers,
            )
            resp.raise_for_status()
            msg = resp.json()

            sender = msg.get("from", {}).get("emailAddress", {})
            body_content = msg.get("body", {}).get("content", "")
            # Strip HTML if content type is HTML
            if msg.get("body", {}).get("contentType", "").lower() == "html":
                body_content = _strip_html(body_content)

            return Email(
                id=msg.get("id", ""),
                subject=msg.get("subject", ""),
                sender=f"{sender.get('name', '')} <{sender.get('address', '')}>",
                date=msg.get("receivedDateTime", ""),
                snippet=msg.get("bodyPreview", ""),
                body=body_content,
            )

    async def create_draft(self, to: str, subject: str, body: str, reply_to: str = "") -> DraftResult:
        client, headers = await self._get_client()
        async with client:
            if reply_to:
                # Create reply draft
                resp = await client.post(
                    f"{GRAPH_API}/me/messages/{reply_to}/createReply",
                    headers=headers,
                )
                resp.raise_for_status()
                reply_msg = resp.json()

                # Update the reply draft with our content
                resp = await client.patch(
                    f"{GRAPH_API}/me/messages/{reply_msg['id']}",
                    json={"body": {"contentType": "text", "content": body}},
                    headers=headers,
                )
                resp.raise_for_status()
                return DraftResult(id=reply_msg["id"])
            else:
                # Create new draft
                draft_body = {
                    "subject": subject,
                    "body": {"contentType": "text", "content": body},
                    "isDraft": True,
                }
                if to:
                    draft_body["toRecipients"] = [{"emailAddress": {"address": addr.strip()}} for addr in to.split(",")]

                resp = await client.post(
                    f"{GRAPH_API}/me/messages",
                    json=draft_body,
                    headers=headers,
                )
                resp.raise_for_status()
                return DraftResult(id=resp.json().get("id", ""))

    async def list_events(self, days: int = 7) -> list[CalendarEvent]:
        client, headers = await self._get_client()
        async with client:
            now = datetime.now(timezone.utc)
            start = now.isoformat()
            end = (now + timedelta(days=days)).isoformat()

            resp = await client.get(
                f"{GRAPH_API}/me/calendarview",
                params={
                    "startdatetime": start,
                    "enddatetime": end,
                    "$select": "id,subject,start,end,location,bodyPreview,attendees",
                    "$orderby": "start/dateTime",
                },
                headers=headers,
            )
            resp.raise_for_status()

            events = []
            for item in resp.json().get("value", []):
                events.append(
                    CalendarEvent(
                        id=item.get("id", ""),
                        title=item.get("subject", ""),
                        start=item.get("start", {}).get("dateTime", ""),
                        end=item.get("end", {}).get("dateTime", ""),
                        location=item.get("location", {}).get("displayName", ""),
                        description=item.get("bodyPreview", ""),
                        attendees=[
                            a.get("emailAddress", {}).get("address", "") for a in item.get("attendees", [])
                        ],
                    )
                )
            return events

    async def create_event(self, title: str, start: str, end: str, description: str = "") -> EventResult:
        client, headers = await self._get_client()
        async with client:
            event_body = {
                "subject": title,
                "start": {"dateTime": start, "timeZone": "UTC"},
                "end": {"dateTime": end, "timeZone": "UTC"},
            }
            if description:
                event_body["body"] = {"contentType": "text", "content": description}

            resp = await client.post(
                f"{GRAPH_API}/me/events",
                json=event_body,
                headers=headers,
            )
            resp.raise_for_status()
            return EventResult(id=resp.json().get("id", ""))


def _strip_html(html: str) -> str:
    """Basic HTML to text conversion."""
    import re

    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<p[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
