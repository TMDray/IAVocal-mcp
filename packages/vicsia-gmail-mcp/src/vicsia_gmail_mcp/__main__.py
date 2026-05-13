"""Entry point for vicsia-gmail-mcp."""

from .server import mcp


def main():
    mcp.run()


if __name__ == "__main__":
    main()
