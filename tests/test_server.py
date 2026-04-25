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


class TestProviderDetection:
    def test_gmail_detected(self):
        import vicsia_email_mcp.server as srv
        srv._provider = None
        with patch("vicsia_email_mcp.auth.google_oauth.has_google_credentials", return_value=True), \
             patch("vicsia_email_mcp.auth.ms_token.has_outlook_credentials", return_value=False):
            provider = srv.get_provider()
            from vicsia_email_mcp.providers.gmail import GmailProvider
            assert isinstance(provider, GmailProvider)

    def test_outlook_detected(self):
        import vicsia_email_mcp.server as srv
        srv._provider = None
        with patch("vicsia_email_mcp.auth.google_oauth.has_google_credentials", return_value=False), \
             patch("vicsia_email_mcp.auth.ms_token.has_outlook_credentials", return_value=True):
            provider = srv.get_provider()
            from vicsia_email_mcp.providers.outlook import OutlookProvider
            assert isinstance(provider, OutlookProvider)

    def test_no_provider_raises(self):
        import vicsia_email_mcp.server as srv
        srv._provider = None
        with patch("vicsia_email_mcp.auth.google_oauth.has_google_credentials", return_value=False), \
             patch("vicsia_email_mcp.auth.ms_token.has_outlook_credentials", return_value=False):
            with pytest.raises(RuntimeError, match="No email provider"):
                srv.get_provider()

    def test_env_var_override(self):
        import vicsia_email_mcp.server as srv
        srv._provider = None
        with patch.dict("os.environ", {"EMAIL_PROVIDER": "outlook"}):
            provider = srv.get_provider()
            from vicsia_email_mcp.providers.outlook import OutlookProvider
            assert isinstance(provider, OutlookProvider)
