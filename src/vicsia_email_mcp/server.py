"""Vicsia Email MCP Server — 5 unified tools for Gmail + Outlook.

Tools:
  - search_emails: Search emails by query
  - read_email: Read full email content
  - create_draft: Create an email draft (never sends)
  - list_events: List upcoming calendar events (beta)
  - create_event: Create a calendar event (beta)

Provider selection: EMAIL_PROVIDER env var ("gmail" | "outlook") — REQUIRED.
Pas d'auto-detection : risque de bleed-over si les deux comptes OAuth ont été
configurés sur la même machine. L'appelant (Vicsia) injecte EMAIL_PROVIDER
explicitement par MCP pour garantir l'isolement Gmail/Outlook.
"""

import logging
import os

from mcp.server.fastmcp import FastMCP

from .providers.base import EmailProvider

logger = logging.getLogger(__name__)

mcp = FastMCP("vicsia-email")

_provider: EmailProvider | None = None


def get_provider() -> EmailProvider:
    """Get or create the email provider (lazy singleton).

    EMAIL_PROVIDER doit être défini explicitement (gmail|outlook).
    Si absent ou invalide → RuntimeError immédiate.
    """
    global _provider
    if _provider is not None:
        return _provider

    provider_name = os.environ.get("EMAIL_PROVIDER", "").lower()

    if provider_name == "gmail":
        from .providers.gmail import GmailProvider

        _provider = GmailProvider()
        logger.info("Email provider: Gmail")
    elif provider_name == "outlook":
        from .providers.outlook import OutlookProvider

        _provider = OutlookProvider()
        logger.info("Email provider: Outlook")
    else:
        raise RuntimeError(
            f"EMAIL_PROVIDER must be 'gmail' or 'outlook' (got: {provider_name!r}). "
            "Set the env var explicitly — no auto-detection."
        )

    return _provider


# ==================== Email Tools ====================


@mcp.tool()
async def search_emails(query: str, max_results: int = 10) -> str:
    """Search emails by query. Returns subject, sender, date, preview for each result."""
    provider = get_provider()
    results = await provider.search_emails(query, min(max_results, 20))

    if not results:
        return "No emails found."

    lines = []
    for i, em in enumerate(results, 1):
        lines.append(f"[{i}] De: {em.sender} | {em.date}")
        lines.append(f"    Objet: {em.subject}")
        lines.append(f"    Apercu: {em.snippet[:150]}")
        lines.append(f"    ID: {em.id}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def read_email(email_id: str) -> str:
    """Read the full content of an email by its ID."""
    provider = get_provider()
    em = await provider.read_email(email_id)

    return (
        f"De: {em.sender}\n"
        f"Date: {em.date}\n"
        f"Objet: {em.subject}\n"
        f"---\n"
        f"{em.body}"
    )


@mcp.tool()
async def create_draft(to: str = "", subject: str = "", body: str = "", reply_to: str = "") -> str:
    """Create an email draft. Does NOT send it. Use reply_to with an email ID to create a reply draft."""
    provider = get_provider()
    result = await provider.create_draft(to, subject, body, reply_to)
    return f"Draft created (id: {result.id})"


# ==================== Calendar Tools (beta) ====================


@mcp.tool()
async def list_events(days: int = 7) -> str:
    """List upcoming calendar events for the next N days. Beta feature."""
    provider = get_provider()
    events = await provider.list_events(min(days, 30))

    if not events:
        return "No events found."

    lines = []
    for ev in events:
        lines.append(f"- {ev.title}")
        lines.append(f"  {ev.start} → {ev.end}")
        if ev.location:
            lines.append(f"  Lieu: {ev.location}")
        if ev.attendees:
            lines.append(f"  Participants: {', '.join(ev.attendees[:5])}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def create_event(title: str, start: str, end: str, description: str = "") -> str:
    """Create a calendar event. Does not send invitations. Beta feature.

    Args:
        title: Event title
        start: Start time (ISO 8601 format, e.g. 2026-04-25T14:00:00)
        end: End time (ISO 8601 format)
        description: Optional event description
    """
    provider = get_provider()
    result = await provider.create_event(title, start, end, description)
    return f"Event created (id: {result.id})"
