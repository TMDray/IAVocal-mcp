# vicsia-outlook-mcp

MCP server exposing Outlook (Microsoft 365) and Outlook Calendar through 6 unified tools, for use with [Vicsia](https://vicsia.app).

## Tools

- `search_emails(query, max_results)` — search Outlook inbox via Microsoft Graph.
- `read_email(email_id, strip_quotes)` — full content of one email.
- `preview_emails(email_ids)` — batch preview of up to 10 emails (for synthesis).
- `create_draft(to, subject, body, reply_to)` — create a draft (never sends).
- `list_events(days)` — list upcoming Outlook Calendar events.
- `create_event(title, start, end, description)` — create a calendar event.

## Authentication

Tokens are stored encrypted in `~/.vicsia/ms365_token.json`. Vicsia handles the OAuth device code flow via the Connexions page.

For standalone usage (outside Vicsia), set `MS365_MCP_CLIENT_ID` env var (your Azure AD app registration ID with "Allow public client flows" enabled).

## Install

```bash
pip install vicsia-outlook-mcp
# or via uvx (recommended):
uvx vicsia-outlook-mcp
```

## License

MIT
