"""Deprecation stub — directs users to vicsia-gmail-mcp or vicsia-outlook-mcp."""

import sys


def main():
    sys.stderr.write(
        "vicsia-email-mcp est déprécié depuis 0.3.0.\n"
        "Installe vicsia-gmail-mcp (Gmail) ou vicsia-outlook-mcp (Outlook) à la place.\n"
        "\n"
        "  pip install vicsia-gmail-mcp     # Gmail + Google Calendar\n"
        "  pip install vicsia-outlook-mcp   # Outlook + Outlook Calendar\n"
        "\n"
        "Vicsia migre automatiquement vers les nouveaux packages — aucune action requise.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
