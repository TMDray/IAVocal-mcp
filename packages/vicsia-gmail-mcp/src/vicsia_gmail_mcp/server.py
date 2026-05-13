"""Vicsia Gmail MCP Server — 6 tools for Gmail + Google Calendar.

Tools:
  - search_emails: Search emails by query
  - read_email: Read full email content
  - preview_emails: Batch preview multiple emails (max 10) for synthesis
  - create_draft: Create an email draft (never sends)
  - list_events: List upcoming calendar events (beta)
  - create_event: Create a calendar event (beta)
"""

import logging

from mcp.server.fastmcp import FastMCP

from .provider import GmailProvider

logger = logging.getLogger(__name__)

mcp = FastMCP("vicsia-gmail")

_provider: GmailProvider | None = None


def _get_provider() -> GmailProvider:
    """Lazy singleton."""
    global _provider
    if _provider is None:
        _provider = GmailProvider()
        logger.info("Email provider: Gmail")
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
    results = await _get_provider().search_emails(query, min(max_results, 30))
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
    em = await _get_provider().read_email(email_id)

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
    provider = _get_provider()

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
    result = await _get_provider().create_draft(to, subject, body, reply_to)
    logger.info("[create_draft] → id=%r", result.id)
    return f"Draft created (id: {result.id})"


# ==================== Calendar Tools (beta) ====================


@mcp.tool()
async def list_events(days: int = 7) -> str:
    """List upcoming calendar events for the next N days. Beta feature."""
    logger.info("[list_events] days=%d", days)
    events = await _get_provider().list_events(min(days, 30))
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
    result = await _get_provider().create_event(title, start, end, description)
    logger.info("[create_event] → id=%r", result.id)
    return f"Event created (id: {result.id})"
