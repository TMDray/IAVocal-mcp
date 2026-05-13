# IAVocal-mcp — MCP servers monorepo for Vicsia

Monorepo hosting MCP servers used by [Vicsia](https://vicsia.app).

## Packages

| Package | Description | Status |
|---------|-------------|--------|
| [`vicsia-gmail-mcp`](packages/vicsia-gmail-mcp/) | Gmail + Google Calendar MCP server | active |
| [`vicsia-outlook-mcp`](packages/vicsia-outlook-mcp/) | Outlook + Outlook Calendar MCP server | active |
| [`vicsia-email-mcp`](packages/vicsia-email-mcp/) | DEPRECATED — split into the two above | v0.3.0 = stub |

## Why split?

Previously, Gmail and Outlook were bundled in a single package with an `EMAIL_PROVIDER` env switch. The split brings:

- Independent dependencies (Gmail-only user doesn't ship Outlook code).
- Independent release cycles (a bug in one provider doesn't block the other).
- Cleaner architecture — one MCP = one PyPI package.

## Development

```bash
# Sync workspace (picks up all packages)
uv sync

# Build a package
cd packages/vicsia-gmail-mcp && uv build

# Test a package
cd packages/vicsia-gmail-mcp && uv run pytest
```

## Convention

See the `/mcp-development` skill in the Vicsia repo for design rules (1 MCP = 1 package, batch tools, cross-platform gotchas, OAuth wiring, etc.).

## License

MIT
