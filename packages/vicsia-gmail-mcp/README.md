# vicsia-gmail-mcp

MCP server exposing Gmail and Google Calendar through 6 unified tools, for use with [Vicsia](https://vicsia.app).

## Tools

- `search_emails(query, max_results)` — search Gmail with Gmail query syntax.
- `read_email(email_id, strip_quotes)` — full content of one email.
- `preview_emails(email_ids)` — batch preview of up to 10 emails (for synthesis).
- `create_draft(to, subject, body, reply_to)` — create a draft (never sends).
- `list_events(days)` — list upcoming Google Calendar events.
- `create_event(title, start, end, description)` — create a calendar event.

## Authentication

Tokens are stored in `~/.google_workspace_mcp/credentials/`. Vicsia handles the OAuth PKCE flow via the Connexions page.

For standalone usage (outside Vicsia), set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` env vars.

## Install

```bash
pip install vicsia-gmail-mcp
# or via uvx (recommended):
uvx vicsia-gmail-mcp
```

## License

MIT
