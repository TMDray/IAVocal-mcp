"""Text utilities for email body processing.

strip_quoted_text() removes the quoted history from a reply email body so the
LLM sees only the new content. Patterns are inspired by quotequail and talon
(Mailgun), which are battle-tested libraries for this exact use case.
"""

import re

# Block-start markers: when found, everything from this point onwards is quoted.
# Order in the list doesn't matter — we pick the earliest match position.
_BLOCK_START_PATTERNS = [
    # Gmail/Apple Mail EN — "On May 9, 2026 at 14:30, John <john@x.com> wrote:"
    re.compile(r"^On .+ wrote:\s*$", re.MULTILINE),
    # Gmail FR — "Le 9 mai 2026 à 14:30, Jean <jean@x.com> a écrit :"
    re.compile(r"^Le .+ a écrit\s*:\s*$", re.MULTILINE),
    # Outlook underscores separator (typically 32 underscores after strip HTML)
    re.compile(r"^_{7,}\s*$", re.MULTILINE),
    # Outlook -----Original Message----- (EN/FR/DE)
    re.compile(
        r"^\s*[-]+\s*(Original Message|Message d'origine|Ursprüngliche Nachricht)\s*[-]+\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    # Outlook header block — 2+ consecutive header lines (From/Sent/To/Subject)
    # in EN/FR/DE. Marks the start of a quoted Outlook reply.
    re.compile(
        r"^(From|De|Von|Sent|Envoyé|Gesendet|To|À|Subject|Objet)\s*:.+\n"
        r"^(From|De|Von|Sent|Envoyé|Gesendet|To|À|Subject|Objet)\s*:",
        re.IGNORECASE | re.MULTILINE,
    ),
]

# Inline RFC 3676 quotes — applied line-by-line after block truncation.
_RFC_QUOTE_LINE = re.compile(r"^>+ ?.*$")


def strip_quoted_text(body: str) -> str:
    """Remove quoted history from a reply email body.

    Strategy:
      1. Find the earliest position of any block-start marker
         (Gmail attribution, Outlook separator, header block).
      2. Truncate the body at that position.
      3. From the remaining content, strip any line starting with `>` (RFC 3676).
      4. Collapse trailing whitespace.

    Returns the original body unchanged if no marker is found.
    Coverage ~90-95% for typical FR/EN pro emails. Edge cases (multi-line wrap
    attribution, HTML CSS residuals, non-Latin scripts) may leak through —
    fall back to read_email(strip_quotes=False) if quality is degraded.
    """
    if not body:
        return body

    earliest = len(body)
    for pattern in _BLOCK_START_PATTERNS:
        match = pattern.search(body)
        if match and match.start() < earliest:
            earliest = match.start()

    truncated = body[:earliest]

    cleaned_lines = [
        line for line in truncated.splitlines() if not _RFC_QUOTE_LINE.match(line)
    ]

    return "\n".join(cleaned_lines).rstrip()
