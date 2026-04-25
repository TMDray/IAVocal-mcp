# Vicsia Email MCP

Minimal MCP server for email and calendar — Gmail + Outlook, 5 unified tools.

## Why

Community MCP servers expose 100-200+ tools. An AI using a small model gets confused with too many options. This MCP exposes **exactly 5 tools** with unified names that work with both Gmail and Outlook.

```
Community MCP:    search_gmail_messages / list-mail-messages    → 2 different names
Vicsia Email MCP: search_emails                                → 1 name, works for both
```

## Tools

| Tool | Description | Params |
|------|-------------|--------|
| `search_emails` | Search emails by query | `query` (str), `max_results` (int, default 10) |
| `read_email` | Read full email content | `email_id` (str) |
| `create_draft` | Create a draft (never sends) | `to`, `subject`, `body`, `reply_to` (optional) |
| `list_events` | List upcoming calendar events (beta) | `days` (int, default 7) |
| `create_event` | Create a calendar event (beta) | `title`, `start`, `end`, `description` |

## Provider detection

The MCP auto-detects which provider to use:

1. `EMAIL_PROVIDER` env var (`gmail` or `outlook`)
2. Google credentials present (`~/.google_workspace_mcp/credentials/`) → Gmail
3. Outlook token present (`~/.vicsia/ms365_token.json`) → Outlook

## Usage with Vicsia

Authentication is handled by Vicsia's Connexions page. The MCP reads tokens from the same locations — no double login needed.

## Usage standalone

```json
{
  "mcpServers": {
    "vicsia-email": {
      "command": "uvx",
      "args": ["vicsia-email-mcp"],
      "env": {
        "EMAIL_PROVIDER": "gmail",
        "GOOGLE_OAUTH_CLIENT_ID": "your-client-id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

## Development

```bash
cd IAVocal-mcp
pip install -e ".[dev]"
pytest
```

## Upstream tracking

Check if upstream MCPs we based our implementation on have changed:

```bash
python scripts/check_upstream.py
```

## License

MIT
