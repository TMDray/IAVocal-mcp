"""Tests for the vicsia-email-mcp server tools."""

from unittest.mock import AsyncMock, patch

import pytest

from vicsia_email_mcp.providers.base import CalendarEvent, DraftResult, Email, EventResult


@pytest.fixture
def mock_gmail_provider():
    from vicsia_email_mcp.providers.base import EmailProvider

    provider = AsyncMock(spec=EmailProvider)
    provider.search_emails.return_value = [
        Email(id="msg1", subject="Reunion", sender="jean@test.com", date="2026-04-25", snippet="Bonjour..."),
        Email(id="msg2", subject="Facture", sender="compta@test.com", date="2026-04-24", snippet="Veuillez..."),
    ]
    provider.read_email.return_value = Email(
        id="msg1", subject="Reunion", sender="jean@test.com", date="2026-04-25", snippet="Bonjour...", body="Bonjour,\n\nJe confirme la reunion."
    )
    provider.create_draft.return_value = DraftResult(id="draft123")
    provider.list_events.return_value = [
        CalendarEvent(id="ev1", title="Standup", start="2026-04-25T09:00", end="2026-04-25T09:30"),
    ]
    provider.create_event.return_value = EventResult(id="ev_new")
    return provider


@pytest.fixture(autouse=True)
def reset_provider():
    """Reset the global provider between tests."""
    import vicsia_email_mcp.server as srv
    srv._provider = None
    yield
    srv._provider = None


class TestSearchEmails:
    @pytest.mark.asyncio
    async def test_returns_formatted_results(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            result = await search_emails("reunion", 10)
            assert "Reunion" in result
            assert "jean@test.com" in result
            assert "msg1" in result

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_gmail_provider):
        mock_gmail_provider.search_emails.return_value = []
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            result = await search_emails("nothing", 10)
            assert "No emails found" in result

    @pytest.mark.asyncio
    async def test_max_results_capped(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            await search_emails("test", 50)
            mock_gmail_provider.search_emails.assert_called_once_with("test", 20)


class TestReadEmail:
    @pytest.mark.asyncio
    async def test_returns_full_content(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import read_email
            result = await read_email("msg1")
            assert "jean@test.com" in result
            assert "Reunion" in result
            assert "Je confirme la reunion" in result


class TestCreateDraft:
    @pytest.mark.asyncio
    async def test_creates_draft(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import create_draft
            result = await create_draft("to@test.com", "Objet", "Contenu")
            assert "draft123" in result
            mock_gmail_provider.create_draft.assert_called_once_with("to@test.com", "Objet", "Contenu", "")

    @pytest.mark.asyncio
    async def test_reply_draft(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import create_draft
            await create_draft("", "", "Ma reponse", reply_to="msg1")
            mock_gmail_provider.create_draft.assert_called_once_with("", "", "Ma reponse", "msg1")


class TestListEvents:
    @pytest.mark.asyncio
    async def test_returns_formatted_events(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import list_events
            result = await list_events(7)
            assert "Standup" in result

    @pytest.mark.asyncio
    async def test_days_capped(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import list_events
            await list_events(60)
            mock_gmail_provider.list_events.assert_called_once_with(30)


class TestCreateEvent:
    @pytest.mark.asyncio
    async def test_creates_event(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import create_event
            result = await create_event("Meeting", "2026-04-25T14:00", "2026-04-25T15:00")
            assert "ev_new" in result


class TestProviderSelection:
    """Sélection du provider via EMAIL_PROVIDER env (requis, pas d'auto-detect)."""

    def test_gmail_via_env(self, monkeypatch):
        import vicsia_email_mcp.server as srv
        srv._provider = None
        monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
        provider = srv.get_provider()
        from vicsia_email_mcp.providers.gmail import GmailProvider
        assert isinstance(provider, GmailProvider)

    def test_outlook_via_env(self, monkeypatch):
        import vicsia_email_mcp.server as srv
        srv._provider = None
        monkeypatch.setenv("EMAIL_PROVIDER", "outlook")
        provider = srv.get_provider()
        from vicsia_email_mcp.providers.outlook import OutlookProvider
        assert isinstance(provider, OutlookProvider)

    def test_missing_env_raises(self, monkeypatch):
        """Sans EMAIL_PROVIDER → RuntimeError immédiate (pas d'auto-detect)."""
        import vicsia_email_mcp.server as srv
        srv._provider = None
        monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
        with pytest.raises(RuntimeError, match="EMAIL_PROVIDER must be"):
            srv.get_provider()

    def test_invalid_value_raises(self, monkeypatch):
        """Valeur invalide (ex: 'google' au lieu de 'gmail') → RuntimeError claire."""
        import vicsia_email_mcp.server as srv
        srv._provider = None
        monkeypatch.setenv("EMAIL_PROVIDER", "google")
        with pytest.raises(RuntimeError, match="EMAIL_PROVIDER must be"):
            srv.get_provider()

    def test_no_bleed_over_when_both_credentials_exist(self, monkeypatch):
        """Même si Gmail ET Outlook OAuth sont configurés, EMAIL_PROVIDER seul décide.

        Garde-fou contre le bleed-over Gmail/Outlook : un utilisateur qui n'a active
        qu'Outlook dans Vicsia ne doit JAMAIS recevoir Gmail comme provider, meme si
        ses credentials Google existent encore sur le disque (OAuth precedent).
        """
        import vicsia_email_mcp.server as srv
        srv._provider = None
        monkeypatch.setenv("EMAIL_PROVIDER", "outlook")
        # Simuler que les deux credentials existent (cas reel apres OAuth Gmail puis Outlook)
        with patch("vicsia_email_mcp.auth.google_oauth.has_google_credentials", return_value=True), \
             patch("vicsia_email_mcp.auth.ms_token.has_outlook_credentials", return_value=True):
            provider = srv.get_provider()
        from vicsia_email_mcp.providers.outlook import OutlookProvider
        from vicsia_email_mcp.providers.gmail import GmailProvider
        assert isinstance(provider, OutlookProvider)
        assert not isinstance(provider, GmailProvider)


class TestEncryptedTokenReading:
    """Verifie que get_outlook_token() peut dechiffrer un token chiffre par Vicsia.

    Bug critique resolu: avant la 0.1.3, _crypto_bridge.py ne pouvait pas
    importer src.core.crypto -> renvoyait le ciphertext brut comme access_token
    -> Bearer 'gAAAAA...' -> 401 Microsoft Graph -> 3 erreurs consecutives.
    """

    def test_decrypts_vicsia_encrypted_token(self, tmp_path, monkeypatch):
        """Token chiffre par Vicsia (Fernet) -> get_outlook_token() retourne le plaintext."""
        import importlib
        import json
        import time

        from cryptography.fernet import Fernet

        # Setup: cle Fernet injectee comme Vicsia le ferait dans le subprocess
        fernet_key = Fernet.generate_key().decode()
        monkeypatch.setenv("VICSIA_FERNET_KEY", fernet_key)

        # Vicsia stocke un token chiffre dans ms365_token.json
        token_path = tmp_path / "ms365_token.json"
        plaintext_access = "ya29.A0AfH6SMBxxx-real-access-token"
        plaintext_refresh = "1//0gxxx-real-refresh-token"
        fernet = Fernet(fernet_key.encode())
        token_path.write_text(
            json.dumps({
                "access_token": fernet.encrypt(plaintext_access.encode()).decode(),
                "refresh_token": fernet.encrypt(plaintext_refresh.encode()).decode(),
                "expires_at": time.time() + 3600,
            })
        )

        # Recharger les modules pour qu'ils prennent VICSIA_FERNET_KEY
        import vicsia_email_mcp.auth._crypto_bridge as bridge
        importlib.reload(bridge)
        import vicsia_email_mcp.auth.ms_token as ms_token
        importlib.reload(ms_token)
        monkeypatch.setattr(ms_token, "MS365_TOKEN_PATH", token_path)

        # Appel: doit dechiffrer et retourner le plaintext
        result = ms_token.get_outlook_token()
        assert result == plaintext_access, (
            f"Expected dechiffre plaintext '{plaintext_access}', got {result!r} "
            "— si commence par 'gAAAAA', le _crypto_bridge n'a pas dechiffre"
        )

    def test_returns_plaintext_token_unchanged(self, tmp_path, monkeypatch):
        """Token stocke en plaintext (legacy / apres refresh subprocess) -> renvoye tel quel."""
        import importlib
        import json
        import time

        # Pas de VICSIA_FERNET_KEY -> mode standalone / plaintext
        monkeypatch.delenv("VICSIA_FERNET_KEY", raising=False)

        token_path = tmp_path / "ms365_token.json"
        token_path.write_text(
            json.dumps({
                "access_token": "ya29.plaintext-token",
                "refresh_token": "1//0g-plaintext",
                "expires_at": time.time() + 3600,
            })
        )

        import vicsia_email_mcp.auth._crypto_bridge as bridge
        importlib.reload(bridge)
        import vicsia_email_mcp.auth.ms_token as ms_token
        importlib.reload(ms_token)
        monkeypatch.setattr(ms_token, "MS365_TOKEN_PATH", token_path)

        result = ms_token.get_outlook_token()
        assert result == "ya29.plaintext-token"

    def test_encrypted_token_without_key_returns_none(self, tmp_path, monkeypatch):
        """Token chiffre + pas de cle Fernet -> token vide -> None (pas de Bearer ciphertext)."""
        import importlib
        import json
        import time

        from cryptography.fernet import Fernet

        # Token chiffre avec une cle, mais subprocess sans VICSIA_FERNET_KEY
        fernet_key = Fernet.generate_key()
        monkeypatch.delenv("VICSIA_FERNET_KEY", raising=False)

        token_path = tmp_path / "ms365_token.json"
        token_path.write_text(
            json.dumps({
                "access_token": Fernet(fernet_key).encrypt(b"plaintext").decode(),
                "refresh_token": "",
                "expires_at": time.time() + 3600,
            })
        )

        import vicsia_email_mcp.auth._crypto_bridge as bridge
        importlib.reload(bridge)
        import vicsia_email_mcp.auth.ms_token as ms_token
        importlib.reload(ms_token)
        monkeypatch.setattr(ms_token, "MS365_TOKEN_PATH", token_path)

        # Sans cle, _decrypt_if_needed retourne "" -> get_outlook_token retourne None
        # (et NON pas le ciphertext brut comme avant le fix)
        result = ms_token.get_outlook_token()
        assert result is None, (
            f"Got {result!r} — devrait etre None pour eviter d'envoyer un ciphertext "
            "comme Bearer token. C'etait LE bug initial."
        )
