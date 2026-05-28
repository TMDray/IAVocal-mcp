"""Gmail provider — direct Google API calls."""

import base64
import email.mime.text
import html as html_mod
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from .auth.google_oauth import get_google_token
from .base import CalendarEvent, DraftResult, Email, EmailProvider, EventResult

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"

_OFFSET_RE = re.compile(r"([+-]\d{2}:?\d{2}|Z)$")


def _to_calendar_datetime(dt_str: str) -> dict:
    """Convert ISO datetime to Google Calendar event datetime format.

    Si offset présent → on l'utilise tel quel (Google le respecte).
    Sinon → ajoute timeZone depuis VICSIA_USER_TZ (défaut UTC) pour éviter
    que Google interprète en TZ du calendrier (souvent ≠ TZ user).
    """
    if _OFFSET_RE.search(dt_str):
        return {"dateTime": dt_str}
    user_tz = os.environ.get("VICSIA_USER_TZ", "UTC")
    return {"dateTime": dt_str, "timeZone": user_tz}


class GmailProvider(EmailProvider):
    """Gmail + Google Calendar provider using REST API directly."""

    async def _get_client(self) -> tuple[httpx.AsyncClient, dict]:
        token = await get_google_token()
        if not token:
            raise RuntimeError("Google not authenticated — connect via Vicsia Connexions page")
        headers = {"Authorization": f"Bearer {token}"}
        return httpx.AsyncClient(timeout=15), headers

    async def search_emails(
        self, query: str, max_results: int = 10, focus_only: bool = True
    ) -> list[Email]:
        client, headers = await self._get_client()
        async with client:
            # Scope INBOX explicite — sans labelIds, /messages couvre TOUTES les
            # boîtes (Sent, Drafts, Spam, Trash) → drafts maison remontent dans
            # les recherches. Analogue au fix Outlook 0.1.4.
            #
            # focus_only=True (défaut) : restreint à l'onglet "Principal" via
            # CATEGORY_PERSONAL. Exclut Promotions / Social / Updates / Forums.
            # Gmail API accepte plusieurs labelIds avec un AND implicite (le mail
            # doit avoir tous les labels).
            label_ids = ["INBOX", "CATEGORY_PERSONAL"] if focus_only else ["INBOX"]
            params: dict = {"q": query, "maxResults": max_results, "labelIds": label_ids}
            logger.info("[gmail] GET %s/messages params=%s focus_only=%s", GMAIL_API, params, focus_only)
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
            # Pour reply: résoudre threadId Gmail + Message-ID header MIME via GET.
            # AVANT (bug): on confondait reply_to (id Gmail interne) avec Message-ID
            # (header SMTP type "<CABx@mail.gmail.com>") → thread cassé côté Gmail
            # ET côté destinataire (le client mail n'enchaîne pas le fil).
            thread_id = ""
            in_reply_to_header = ""
            references_header = ""
            if reply_to:
                meta_resp = await client.get(
                    f"{GMAIL_API}/messages/{reply_to}",
                    params={
                        "format": "metadata",
                        "metadataHeaders": ["Message-ID", "References", "Subject"],
                    },
                    headers=headers,
                )
                meta_resp.raise_for_status()
                meta = meta_resp.json()
                thread_id = meta.get("threadId", "")
                msg_headers = meta.get("payload", {}).get("headers", [])
                in_reply_to_header = next(
                    (h["value"] for h in msg_headers if h.get("name", "").lower() == "message-id"),
                    "",
                )
                # References = anciennes References + le Message-ID actuel (chaîne du fil)
                prev_refs = next(
                    (h["value"] for h in msg_headers if h.get("name", "").lower() == "references"),
                    "",
                )
                references_header = f"{prev_refs} {in_reply_to_header}".strip()
                # Sujet: "Re: ..." si l'original n'avait pas déjà un Re:
                if not subject:
                    orig_subject = next(
                        (h["value"] for h in msg_headers if h.get("name", "").lower() == "subject"),
                        "",
                    )
                    if orig_subject and not orig_subject.lower().startswith("re:"):
                        subject = f"Re: {orig_subject}"
                    else:
                        subject = orig_subject

            mime = email.mime.text.MIMEText(body, "plain", "utf-8")
            mime["To"] = to
            mime["Subject"] = subject
            if in_reply_to_header:
                mime["In-Reply-To"] = in_reply_to_header
            if references_header:
                mime["References"] = references_header

            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

            draft_body: dict = {"message": {"raw": raw}}
            if thread_id:
                draft_body["message"]["threadId"] = thread_id

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
            # _to_calendar_datetime: si offset présent, on l'utilise tel quel ;
            # sinon ajoute timeZone (VICSIA_USER_TZ ou UTC) pour éviter que Google
            # interprète selon la TZ du calendrier (souvent ≠ TZ user).
            event_body: dict = {
                "summary": title,
                "start": _to_calendar_datetime(start),
                "end": _to_calendar_datetime(end),
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
        labels=list(msg_data.get("labelIds", [])),
    )


def _parse_email_full(msg_data: dict) -> Email:
    em = _parse_email_metadata(msg_data)

    # Extract body from payload
    payload = msg_data.get("payload", {})
    body = _extract_body(payload)
    em.body = body or em.snippet
    return em


def _extract_body(payload: dict) -> str:
    """Extract text body from Gmail payload (handles multipart + HTML fallback).

    60-80% des emails (newsletters, transactionnels) sont text/html only.
    Sans décodage HTML côté client, on retombait sur le snippet (~150 char)
    au lieu du contenu complet. Gmail n'a pas d'équivalent au header
    Prefer:outlook.body-content-type=text de Microsoft Graph, donc on décode ici.
    """
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            # Drop le contenu de <script> et <style> (sinon CSS/JS dans le texte)
            text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
            # Strip toutes les autres tags
            text = re.sub(r"<[^>]+>", " ", text)
            # Normalise les blancs et décode les entités (&nbsp; &eacute; &#8217; etc.)
            text = re.sub(r"\s+", " ", text).strip()
            return html_mod.unescape(text)

    if mime_type.startswith("multipart/"):
        # Privilégier text/plain quand un alternative est dispo
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                body = _extract_body(part)
                if body:
                    return body
        # Sinon, n'importe quoi qui ait du contenu (récursion sur multipart imbriqué)
        for part in parts:
            body = _extract_body(part)
            if body:
                return body

    return ""
