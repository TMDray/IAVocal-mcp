"""Entry point for vicsia-email-mcp."""

from .server import mcp


def main():
    mcp.run()


if __name__ == "__main__":
    main()
