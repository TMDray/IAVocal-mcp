"""Vicsia Outlook MCP Server — 6 tools for Outlook + Outlook Calendar.

Tools:
  - search_emails: Search emails by query
  - read_email: Read full email content
  - preview_emails: Batch preview multiple emails (max 5) for synthesis
  - create_draft: Create an email draft (never sends)
  - list_events: List upcoming calendar events (beta)
  - create_event: Create a calendar event (beta)
"""

import logging

from mcp.server.fastmcp import FastMCP

from .provider import OutlookProvider

logger = logging.getLogger(__name__)

mcp = FastMCP("vicsia-outlook")

_provider: OutlookProvider | None = None


def _get_provider() -> OutlookProvider:
    """Lazy singleton."""
    global _provider
    if _provider is None:
        _provider = OutlookProvider()
        logger.info("Email provider: Outlook")
    return _provider


# ==================== Email Tools ====================


@mcp.tool()
async def search_emails(query: str, max_results: int = 5, focus_only: bool = True) -> str:
    """Search emails by query. Returns ID, sender, date, subject and a short snippet.

    TOKEN BUDGET: default max_results=5 (covers most use cases). Hard cap at 5 — never exceeds.

    INBOX SCOPE (focus_only):
      - True (default): only "Focused" inbox (Outlook's auto-prioritized mails — excludes
        newsletters/notifications classified as "Other"). This is what you want 99% of the time.
      - False: include all mails (Focused + Other). Use only if user explicitly asks for
        newsletters/promotions ("show me my marketing emails").

    DATE FILTERING: add date constraints to the query to limit results to recent emails:
      - "received>=2026-05-20" → since May 20th
      - "received>=2026-05-01 AND received<=2026-05-31" → during May
    For recent emails, always add a date filter to avoid loading old irrelevant messages.
    Examples: "is:unread received>=2026-05-20", "from:jean subject:facture received>=2026-04-01"

    IMPORTANT: After getting results, use preview_emails([id1, id2, ...]) to get content.
    Do NOT use read_email in a loop — use preview_emails for batch reading.

    Args:
        query: Outlook search query (KQL syntax)
        max_results: Max emails (default 5). Hard cap: 5.
        focus_only: Restrict to "Focused" inbox (default True). Excludes "Other" classified mails.
    """
    logger.info("[search_emails] query=%r max_results=%d focus_only=%s", query, max_results, focus_only)
    results = await _get_provider().search_emails(query, min(max_results, 5), focus_only=focus_only)
    logger.info("[search_emails] → count=%d", len(results))

    if not results:
        return "No emails found."

    lines = []
    for em in results:
        lines.append(f"ID: {em.id}")
        lines.append(f"De: {em.sender} | {em.date}")
        lines.append(f"Objet: {em.subject}")
        lines.append(f"Apercu: {em.snippet[:150]}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def read_email(email_id: str, strip_quotes: bool = False) -> str:
    """Read the FULL content of ONE email by its ID.

    USE THIS for: reading a single email in full detail, replying to a specific thread
    (strip_quotes=False preserves the quoted history for reply context).

    DO NOT USE THIS in a loop — use preview_emails([id1, id2, ...]) for multiple emails.

    Args:
        email_id: The ID value from search_emails results (the "ID:" line, not the result number).
        strip_quotes: False (default) = full body with reply chain. True = new content only.
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
async def preview_emails(email_ids: list[str], focus_only: bool = True) -> str:
    """Get compact previews of recent emails for synthesis or overview.

    USE THIS WHEN:
    - The user asks to summarize or synthesize multiple emails ("résume mes mails clients")
    - The user wants an overview of recent emails ("que disent mes emails de la semaine ?")
    - After search_emails, you need just enough content to write a synthesis

    DO NOT USE FOR:
    - Finding emails — use search_emails instead
    - Replying to a thread — use read_email instead (preserves reply chain)

    INBOX SCOPE (focus_only):
    - True (default): skip emails classified as "Other" by Outlook. If you pass IDs that turn
      out to be non-focused, they are excluded with a note. Coherent with search_emails(focus_only=True).
    - False: preview all emails regardless of classification.

    Max 8 email IDs. Only pass IDs from RECENT emails (from current search results).
    Returns ~150 chars of body per email — enough for synthesis, minimal token cost.
    Quoted history is automatically stripped.

    After calling preview_emails, you have enough data → declare done=true immediately.

    Args:
        email_ids: List of email IDs from search_emails results. Max 8.
        focus_only: Restrict to "Focused" inbox (default True). Non-focused emails are skipped.
    """
    from .text_utils import strip_quoted_text

    ids = email_ids[:8]
    logger.info("[preview_emails] count=%d (requested=%d) focus_only=%s", len(ids), len(email_ids), focus_only)
    provider = _get_provider()

    lines = []
    shown_count = 0
    skipped_count = 0
    for i, email_id in enumerate(ids, 1):
        try:
            em = await provider.read_email(email_id)
            # focus_only : skip si le mail n'est pas classé "focused" par Outlook
            if focus_only and "focused" not in em.labels:
                skipped_count += 1
                logger.info("[preview_emails] skip %s (labels=%s, not focused)", email_id, em.labels)
                continue
            body = strip_quoted_text(em.body or "")
            preview = body[:150]
            if len(body) > 150:
                preview += "…"
            shown_count += 1
            lines.append(f"[{shown_count}] De: {em.sender} | {em.date}")
            lines.append(f"    Objet: {em.subject}")
            lines.append(f"    Contenu: {preview}")
            lines.append(f"    ID: {em.id}")
        except Exception as exc:
            lines.append(f"[{i}] ID {email_id!r}: erreur — {exc}")
        lines.append("")

    if focus_only and skipped_count > 0:
        lines.append(f"Note : {skipped_count} mail(s) ignoré(s) (non classés Prioritaires par Outlook).")
    logger.info("[preview_emails] → done shown=%d skipped=%d", shown_count, skipped_count)
    return "\n".join(lines)


@mcp.tool()
async def create_draft(to: str = "", subject: str = "", body: str = "", reply_to: str = "") -> str:
    """Create an email draft. Does NOT send it.

    RETURN FORMAT: Always returns the full draft content (to, subject, body) on both success
    AND failure. This guarantees the user always sees what was written in the capsule — even
    if the draft creation fails (API down, auth expired), they have the content to copy-paste
    or retry. Declare done=true immediately after this call.

    Args:
        to: Recipient email. Use "" or "À compléter" if unknown — user will fill it in Outlook.
        subject: Email subject.
        body: Email body (plain text).
        reply_to: Email ID to reply to (creates a threaded reply draft).
    """
    logger.info(
        "[create_draft] to=%r subject_len=%d body_len=%d reply_to=%r",
        to, len(subject), len(body), reply_to,
    )
    content_block = (
        f"À : {to or 'À compléter'}\n"
        f"Objet : {subject or '(sans objet)'}\n\n"
        f"{body}"
    )
    try:
        result = await _get_provider().create_draft(to, subject, body, reply_to)
        logger.info("[create_draft] → id=%r", result.id)
        return f"Brouillon créé (id: {result.id}).\n\n{content_block}"
    except Exception as exc:
        logger.exception("[create_draft] échec : %s", exc)
        return f"ÉCHEC : {exc}\n\nContenu prévu :\n{content_block}"


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

    CONFIRMATION: Returns "Event created (id: <event_id>)" on success — no verification needed.

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
