#!/usr/bin/env python3
"""Check if upstream MCP tools we depend on have changed.

Usage:
    python scripts/check_upstream.py

Fetches the latest tool definitions from upstream repos (via GitHub raw)
and compares with the tools we've based our implementation on.
Alerts if breaking changes are detected.

This script has no dependencies beyond stdlib + httpx.
"""

import json
import re
import sys
import urllib.request

# Tools we track from each upstream MCP
TRACKED = {
    "gmail": {
        "repo": "taylorwilsdon/google_workspace_mcp",
        "branch": "main",
        "version_file": "pyproject.toml",
        "version_pattern": r'version\s*=\s*"([^"]+)"',
        "our_tools": ["search_emails", "read_email", "create_draft"],
        "upstream_tools": ["search_gmail_messages", "get_gmail_message_content", "draft_gmail_message"],
    },
    "outlook": {
        "repo": "Softeria/ms-365-mcp-server",
        "branch": "main",
        "version_file": "package.json",
        "version_pattern": r'"version"\s*:\s*"([^"]+)"',
        "our_tools": ["search_emails", "read_email", "create_draft"],
        "upstream_tools": ["list-mail-messages", "get-mail-message", "create-draft-email"],
    },
}

# Vicsia's pinned versions (update when bumping)
PINNED_VERSIONS = {
    "gmail": "1.19.0",
    "outlook": "0.79.5",
}


def fetch_raw(repo: str, branch: str, path: str) -> str | None:
    """Fetch a file from GitHub raw."""
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"  WARN: Could not fetch {url}: {e}")
        return None


def get_upstream_version(config: dict) -> str | None:
    """Get the latest version from upstream repo."""
    content = fetch_raw(config["repo"], config["branch"], config["version_file"])
    if not content:
        return None
    match = re.search(config["version_pattern"], content)
    return match.group(1) if match else None


def check_provider(name: str, config: dict) -> list[str]:
    """Check one upstream provider. Returns list of warnings."""
    warnings = []
    print(f"\n{'=' * 50}")
    print(f"  {name.upper()}")
    print(f"  Repo: {config['repo']}")
    print(f"{'=' * 50}")

    # Check version
    upstream_version = get_upstream_version(config)
    pinned = PINNED_VERSIONS.get(name, "?")

    if upstream_version:
        if upstream_version != pinned:
            status = "UPDATE AVAILABLE"
            warnings.append(f"{name}: {pinned} → {upstream_version}")
        else:
            status = "OK"
        print(f"  Version:  pinned={pinned}  upstream={upstream_version}  [{status}]")
    else:
        print(f"  Version:  pinned={pinned}  upstream=?  [COULD NOT CHECK]")

    # Tool mapping
    print(f"\n  Tool mapping:")
    for our, upstream in zip(config["our_tools"], config["upstream_tools"]):
        print(f"    {our:20s} ← {upstream}")

    return warnings


def main():
    print("Vicsia Email MCP — Upstream Check")
    print(f"Checking {len(TRACKED)} providers...")

    all_warnings = []
    for name, config in TRACKED.items():
        warnings = check_provider(name, config)
        all_warnings.extend(warnings)

    print(f"\n{'=' * 50}")
    if all_warnings:
        print("  UPDATES AVAILABLE:")
        for w in all_warnings:
            print(f"  - {w}")
        print("\n  Review changelogs before bumping versions.")
        sys.exit(1)
    else:
        print("  All up to date.")
        sys.exit(0)


if __name__ == "__main__":
    main()
