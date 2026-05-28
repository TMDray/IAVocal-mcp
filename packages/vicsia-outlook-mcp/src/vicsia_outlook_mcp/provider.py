"""Outlook/MS365 provider — direct Microsoft Graph API calls."""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from .auth.ms_token import get_outlook_token
from .base import CalendarEvent, DraftResult, Email, EmailProvider, EventResult

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.microsoft.com/v1.0"

_OFFSET_RE = re.compile(r"([+-]\d{2}:?\d{2}|Z)$")


def _to_graph_datetime(dt_str: str) -> dict:
    """Convert an ISO datetime to Graph's dateTimeTimeZone format.

    Si dt_str contient un offset (ex: +02:00 ou Z) → conversion en UTC pour éviter
    le double-décalage avec timeZone. Sinon → utilise VICSIA_USER_TZ (défaut UTC).
    """
    if _OFFSET_RE.search(dt_str):
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            utc = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            return {"dateTime": utc, "timeZone": "UTC"}
        except ValueError:
            pass  # ISO invalide — laisse Graph répondre 400
    user_tz = os.environ.get("VICSIA_USER_TZ", "UTC")
    return {"dateTime": dt_str, "timeZone": user_tz}


class OutlookProvider(EmailProvider):
    """Outlook / Microsoft 365 provider using Graph API directly."""

    async def _get_client(self) -> tuple[httpx.AsyncClient, dict]:
        token = get_outlook_token()
        if not token:
            raise RuntimeError("Outlook not authenticated — connect via Vicsia Connexions page")
        headers = {"Authorization": f"Bearer {token}"}
        return httpx.AsyncClient(timeout=15), headers

    async def search_emails(
        self, query: str, max_results: int = 10, focus_only: bool = True
    ) -> list[Email]:
        client, headers = await self._get_client()
        async with client:
            # Graph API: $search and $filter ne se combinent pas (limitation MS Graph).
            # Stratégie :
            #  - Query vide → on peut combiner $filter (focus) + $orderby
            #  - Query présente → $search + filtrage focused côté Python (post-réception)
            # Dans les deux cas, on sélectionne inferenceClassification pour pouvoir filtrer.
            has_query = bool(query and query.lower() not in ("inbox", "all", "*"))
            params: dict = {
                "$top": max_results,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,inferenceClassification",
            }
            if has_query:
                params["$search"] = f'"{query}"'
                # $filter incompatible avec $search → filtrage post-réception ci-dessous
            else:
                params["$orderby"] = "receivedDateTime desc"
                if focus_only:
                    # focus_only=True (défaut) : restreint à la Focused Inbox d'Outlook
                    # (sélection automatique MS basée sur l'historique de l'utilisateur)
                    params["$filter"] = "inferenceClassification eq 'focused'"

            # Scope explicite à Inbox — /me/messages couvre toute la mailbox
            # (drafts, sent, deleted, clutter) et $search aussi malgré la doc MS.
            url = f"{GRAPH_API}/me/mailFolders/inbox/messages"
            logger.info(
                "[outlook] GET %s params=%s focus_only=%s",
                url,
                {k: v for k, v in params.items() if k != "$select"},
                focus_only,
            )
            resp = await client.get(url, params=params, headers=headers)
            logger.info("[outlook] ← status=%d", resp.status_code)
            resp.raise_for_status()

            results = []
            for msg in resp.json().get("value", []):
                # Filtrage côté Python si on avait $search (incompatible $filter)
                if focus_only and has_query:
                    classification = msg.get("inferenceClassification", "focused")
                    if classification != "focused":
                        continue
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
                if len(results) >= max_results:
                    break
            return results

    async def read_email(self, email_id: str) -> Email:
        client, headers = await self._get_client()
        async with client:
            # Prefer header: Graph fait la conversion HTML→texte côté serveur,
            # bien plus robuste qu'un strip maison (gère style/script/entities,
            # newsletters, formats Outlook spécifiques).
            req_headers = {**headers, "Prefer": 'outlook.body-content-type="text"'}
            resp = await client.get(
                f"{GRAPH_API}/me/messages/{email_id}",
                params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview"},
                headers=req_headers,
            )
            resp.raise_for_status()
            msg = resp.json()

            sender = msg.get("from", {}).get("emailAddress", {})
            return Email(
                id=msg.get("id", ""),
                subject=msg.get("subject", ""),
                sender=f"{sender.get('name', '')} <{sender.get('address', '')}>",
                date=msg.get("receivedDateTime", ""),
                snippet=msg.get("bodyPreview", ""),
                body=msg.get("body", {}).get("content", ""),
            )

    async def create_draft(self, to: str, subject: str, body: str, reply_to: str = "") -> DraftResult:
        client, headers = await self._get_client()
        async with client:
            if reply_to:
                # createReply avec 'comment' insère le texte AU-DESSUS du quote — Graph
                # construit le draft avec l'historique cité préservé. C'est la voie
                # documentée. Le PATCH body écrasait tout le quote → perte de contexte.
                resp = await client.post(
                    f"{GRAPH_API}/me/messages/{reply_to}/createReply",
                    json={"comment": body},
                    headers=headers,
                )
                resp.raise_for_status()
                return DraftResult(id=resp.json().get("id", ""))
            else:
                draft_body: dict = {
                    "subject": subject,
                    "body": {"contentType": "text", "content": body},
                }
                if to:
                    addresses = [addr.strip() for addr in to.split(",") if addr.strip()]
                    if addresses:
                        draft_body["toRecipients"] = [
                            {"emailAddress": {"address": addr}} for addr in addresses
                        ]

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
            event_body: dict = {
                "subject": title,
                "start": _to_graph_datetime(start),
                "end": _to_graph_datetime(end),
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
