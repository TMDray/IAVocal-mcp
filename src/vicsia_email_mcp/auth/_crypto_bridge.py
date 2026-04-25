"""Bridge to Vicsia's crypto module for token decryption.

This is optional — if Vicsia's crypto module is not on the Python path,
the MCP falls back to plaintext token handling.
"""

try:
    from src.core.crypto import decrypt, encrypt, is_encrypted  # noqa: F401
except ImportError:

    def decrypt(value: str) -> str:
        return value

    def encrypt(value: str) -> str:
        return value

    def is_encrypted(value: str) -> bool:
        return False
