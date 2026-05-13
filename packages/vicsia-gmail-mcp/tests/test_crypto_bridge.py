"""Tests for _crypto_bridge.py — Fernet decryption with VICSIA_FERNET_KEY.

Bug critique resolu: le subprocess uvx vicsia-email-mcp ne pouvait pas dechiffrer
les tokens OAuth stockes par Vicsia (Fernet) car src.core.crypto n'est pas sur
le PYTHONPATH du subprocess. Sans VICSIA_FERNET_KEY injectee, le ciphertext brut
etait envoye comme Bearer token -> 401 Microsoft Graph.
"""

import importlib

import pytest
from cryptography.fernet import Fernet


def _reload_bridge(monkeypatch, key: str | None):
    """Reload _crypto_bridge with a specific VICSIA_FERNET_KEY env."""
    if key is None:
        monkeypatch.delenv("VICSIA_FERNET_KEY", raising=False)
    else:
        monkeypatch.setenv("VICSIA_FERNET_KEY", key)
    import vicsia_gmail_mcp.auth._crypto_bridge as bridge

    return importlib.reload(bridge)


@pytest.fixture
def fernet_key() -> str:
    """Generate a fresh Fernet key for tests (base64 str)."""
    return Fernet.generate_key().decode()


class TestIsEncrypted:
    def test_detects_fernet_prefix(self, monkeypatch, fernet_key):
        bridge = _reload_bridge(monkeypatch, fernet_key)
        ciphertext = Fernet(fernet_key.encode()).encrypt(b"hello").decode()
        assert bridge.is_encrypted(ciphertext) is True

    def test_plaintext_not_encrypted(self, monkeypatch, fernet_key):
        bridge = _reload_bridge(monkeypatch, fernet_key)
        assert bridge.is_encrypted("ya29.A0AfH6SMBxxx") is False
        assert bridge.is_encrypted("plain-token") is False

    def test_empty_not_encrypted(self, monkeypatch, fernet_key):
        bridge = _reload_bridge(monkeypatch, fernet_key)
        assert bridge.is_encrypted("") is False


class TestDecrypt:
    def test_decrypt_with_valid_key(self, monkeypatch, fernet_key):
        """Token chiffre + cle valide -> plaintext dechiffre."""
        bridge = _reload_bridge(monkeypatch, fernet_key)
        ciphertext = Fernet(fernet_key.encode()).encrypt(b"my-secret-token").decode()
        assert bridge.decrypt(ciphertext) == "my-secret-token"

    def test_decrypt_without_key_returns_empty_for_encrypted(self, monkeypatch, fernet_key):
        """Token chiffre + pas de cle -> '' (caller doit re-auth, pas envoyer ciphertext)."""
        # Generer un ciphertext avec une cle quelconque
        ciphertext = Fernet(fernet_key.encode()).encrypt(b"my-secret-token").decode()
        # Recharger le bridge SANS cle
        bridge = _reload_bridge(monkeypatch, None)
        assert bridge.decrypt(ciphertext) == ""

    def test_decrypt_plaintext_passes_through(self, monkeypatch, fernet_key):
        """Valeur non Fernet -> renvoyee telle quelle (compat backward / refresh storage)."""
        bridge = _reload_bridge(monkeypatch, fernet_key)
        assert bridge.decrypt("ya29.A0AfH6SMBxxx") == "ya29.A0AfH6SMBxxx"
        assert bridge.decrypt("plain-token") == "plain-token"

    def test_decrypt_empty_passes_through(self, monkeypatch, fernet_key):
        bridge = _reload_bridge(monkeypatch, fernet_key)
        assert bridge.decrypt("") == ""

    def test_decrypt_invalid_token_returns_empty(self, monkeypatch, fernet_key):
        """Ciphertext avec mauvaise cle -> '' (pas d'exception qui leak)."""
        bridge = _reload_bridge(monkeypatch, fernet_key)
        # Ciphertext genere avec une AUTRE cle -> InvalidToken
        other_key = Fernet.generate_key()
        bad_ciphertext = Fernet(other_key).encrypt(b"data").decode()
        assert bridge.decrypt(bad_ciphertext) == ""

    def test_decrypt_invalid_key_format(self, monkeypatch):
        """VICSIA_FERNET_KEY mal formee -> _fernet=None -> graceful fallback."""
        bridge = _reload_bridge(monkeypatch, "not-a-valid-fernet-key")
        # Plaintext passe quand meme
        assert bridge.decrypt("plain") == "plain"
        # Encrypted ne peut pas etre dechiffre -> ""
        assert bridge.decrypt("gAAAAAfake") == ""


class TestEncrypt:
    def test_encrypt_with_valid_key(self, monkeypatch, fernet_key):
        bridge = _reload_bridge(monkeypatch, fernet_key)
        ciphertext = bridge.encrypt("my-token")
        assert ciphertext != "my-token"
        assert ciphertext.startswith("gAAAAA")

    def test_encrypt_without_key_passes_through(self, monkeypatch):
        """Sans cle (mode standalone), encrypt = no-op (compat)."""
        bridge = _reload_bridge(monkeypatch, None)
        assert bridge.encrypt("my-token") == "my-token"

    def test_encrypt_empty_returns_empty(self, monkeypatch, fernet_key):
        bridge = _reload_bridge(monkeypatch, fernet_key)
        assert bridge.encrypt("") == ""


class TestRoundtrip:
    def test_encrypt_decrypt_roundtrip(self, monkeypatch, fernet_key):
        """encrypt(x) puis decrypt() recupere x."""
        bridge = _reload_bridge(monkeypatch, fernet_key)
        original = "my-secret-token-12345"
        ciphertext = bridge.encrypt(original)
        assert bridge.decrypt(ciphertext) == original

    def test_unicode_roundtrip(self, monkeypatch, fernet_key):
        """Tokens avec caracteres speciaux -> roundtrip OK."""
        bridge = _reload_bridge(monkeypatch, fernet_key)
        original = "tøkén-spëcial-日本語"
        ciphertext = bridge.encrypt(original)
        assert bridge.decrypt(ciphertext) == original


class TestVicsiaCompatibility:
    """Verifie la compat avec les tokens chiffres par src.core.crypto de Vicsia."""

    def test_decrypts_token_from_vicsia_format(self, monkeypatch, fernet_key):
        """Un token chiffre par Vicsia (Fernet standard) doit etre dechiffrable.

        Garantit que le format de ciphertext Fernet est identique des deux cotes
        (Vicsia src.core.crypto et IAVocal-mcp _crypto_bridge utilisent tous deux
        cryptography.fernet.Fernet avec la meme cle).
        """
        # Simule ce que Vicsia stocke
        token_plaintext = "ya29.A0AfH6SMBxxx-vicsia-stored-token"
        ciphertext_from_vicsia = Fernet(fernet_key.encode()).encrypt(token_plaintext.encode()).decode()

        # Le subprocess (recharge avec la cle injectee) doit dechiffrer
        bridge = _reload_bridge(monkeypatch, fernet_key)
        assert bridge.decrypt(ciphertext_from_vicsia) == token_plaintext
