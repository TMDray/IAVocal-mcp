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
    """Search emails by query. Returns ID, sender, date, subject and a short preview.

    IMPORTANT: To read an email's full content, use read_email(email_id=<ID>) where
    <ID> is the value on the "ID:" line below — NOT the result number.
    To read/summarize multiple emails at once, prefer preview_emails([id1, id2, ...]).
    """
    logger.info("[search_emails] query=%r max_results=%d", query, max_results)
    provider = get_provider()
    results = await provider.search_emails(query, min(max_results, 30))
    logger.info("[search_emails] → count=%d", len(results))

    if not results:
        return "No emails found."

    lines = []
    for em in results:
        lines.append(f"ID: {em.id}")
        lines.append(f"De: {em.sender} | {em.date}")
        lines.append(f"Objet: {em.subject}")
        lines.append(f"Apercu: {em.snippet[:100]}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def read_email(email_id: str, strip_quotes: bool = False) -> str:
    """Read the FULL content of ONE email by its ID.

    USE THIS for: reading a single email in full detail, replying to a thread
    (strip_quotes=False preserves the quoted history for context).

    DO NOT USE THIS to read multiple emails one by one — use preview_emails([id1, id2, ...])
    instead, which fetches N emails in a single call and is far more efficient.

    Args:
        email_id: The ID value from search_emails results (the "ID:" line, not the result number).
        strip_quotes: False (default) = full body including reply chain.
                      True = new content only, quoted history stripped.
    """
    logger.info("[read_email] email_id=%r strip_quotes=%s", email_id, strip_quotes)
    provider = get_provider()
    em = await provider.read_email(email_id)

    body = em.body or ""
    if strip_quotes:
        from .text_utils import strip_quoted_text
        body = strip_quoted_text(body)

    logger.info("[read_email] → subject=%r body_len=%d stripped=%s", em.subject, len(body), strip_quotes)

    return (
        f"De: {em.sender}\n"
        f"Date: {em.date}\n"
        f"Objet: {em.subject}\n"
        f"---\n"
        f"{body}"
    )


@mcp.tool()
async def preview_emails(email_ids: list[str]) -> str:
    """Get medium-detail previews of specific emails for synthesis or batch analysis.

    USE THIS WHEN:
    - The user asks to summarize or synthesize multiple emails ("résume mes mails clients")
    - The user asks for an overview of several emails ("que disent mes emails de la semaine ?")
    - You need to compare or analyze 2-10 emails together
    - After search_emails, you identified relevant IDs and want enough content to synthesize

    DO NOT USE FOR:
    - Finding or listing emails — use search_emails instead
    - Reading one email in full detail — use read_email instead
    - Replying to a thread — use read_email (which preserves quoted history)

    Returns ~400 chars of body per email (vs ~100 chars in search_emails, vs full body in read_email).
    Quoted history is automatically stripped — only the new content of each email is shown.
    Maximum 10 email IDs per call to keep context manageable.

    Args:
        email_ids: List of email IDs from search_emails results. Max 10.
    """
    from .text_utils import strip_quoted_text

    ids = email_ids[:10]
    logger.info("[preview_emails] count=%d (requested=%d)", len(ids), len(email_ids))
    provider = get_provider()

    lines = []
    for i, email_id in enumerate(ids, 1):
        try:
            em = await provider.read_email(email_id)
            body = strip_quoted_text(em.body or "")
            preview = body[:400]
            if len(body) > 400:
                preview += "…"
            lines.append(f"[{i}] De: {em.sender} | {em.date}")
            lines.append(f"    Objet: {em.subject}")
            lines.append(f"    Contenu: {preview}")
            lines.append(f"    ID: {em.id}")
        except Exception as exc:
            lines.append(f"[{i}] ID {email_id!r}: erreur — {exc}")
        lines.append("")

    logger.info("[preview_emails] → done %d emails", len(ids))
    return "\n".join(lines)


@mcp.tool()
async def create_draft(to: str = "", subject: str = "", body: str = "", reply_to: str = "") -> str:
    """Create an email draft. Does NOT send it. Use reply_to with an email ID to create a reply draft."""
    logger.info(
        "[create_draft] to=%r subject_len=%d body_len=%d reply_to=%r",
        to, len(subject), len(body), reply_to,
    )
    provider = get_provider()
    result = await provider.create_draft(to, subject, body, reply_to)
    logger.info("[create_draft] → id=%r", result.id)
    return f"Draft created (id: {result.id})"


# ==================== Calendar Tools (beta) ====================


@mcp.tool()
async def list_events(days: int = 7) -> str:
    """List upcoming calendar events for the next N days. Beta feature."""
    logger.info("[list_events] days=%d", days)
    provider = get_provider()
    events = await provider.list_events(min(days, 30))
    logger.info("[list_events] → count=%d", len(events))

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
    logger.info("[create_event] title=%r start=%r end=%r", title, start, end)
    provider = get_provider()
    result = await provider.create_event(title, start, end, description)
    logger.info("[create_event] → id=%r", result.id)
    return f"Event created (id: {result.id})"
