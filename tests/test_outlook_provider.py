"""Tests for OutlookProvider — verify Graph API endpoints and parameters.

Bug critique resolu (0.1.4): search_emails interrogeait /me/messages qui couvre
toute la mailbox (Inbox + Drafts + Sent + Deleted + Clutter) — les brouillons
remontaient comme "emails recents". Fix: scope explicite a /me/mailFolders/inbox/messages.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchEmailsScopedToInbox:
    """search_emails doit interroger UNIQUEMENT le dossier Inbox.

    Garde-fou contre regression: si quelqu'un revient a /me/messages, ce test
    casse immediatement.
    """

    @pytest.mark.asyncio
    async def test_search_emails_uses_inbox_folder_endpoint(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.search_emails("test", 10)

        called_url = mock_client.get.call_args[0][0]
        assert called_url.endswith("/me/mailFolders/inbox/messages"), (
            f"search_emails doit interroger l'Inbox uniquement, pas toute la mailbox. "
            f"URL appelee: {called_url}"
        )
        assert "/me/messages" not in called_url or "mailFolders" in called_url

    @pytest.mark.asyncio
    async def test_search_emails_passes_search_param(self):
        """Verifie que $search est bien passe en query string."""
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.search_emails("facture", 5)

        params = mock_client.get.call_args.kwargs["params"]
        assert params["$search"] == '"facture"'
        assert params["$top"] == 5
        assert "$orderby" not in params  # $search et $orderby incompatibles sur Graph

    @pytest.mark.asyncio
    async def test_search_emails_orderby_when_no_query(self):
        """Sans query reelle (inbox/all/*), on ordonne par date desc."""
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.search_emails("inbox", 10)

        params = mock_client.get.call_args.kwargs["params"]
        assert params["$orderby"] == "receivedDateTime desc"
        assert "$search" not in params


class TestReadEmailKeepsFullMailboxAccess:
    """read_email doit pouvoir lire un message dans n'importe quel dossier
    (notamment Drafts pour replies, Sent pour relectures). Pas de scope Inbox.
    """

    @pytest.mark.asyncio
    async def test_read_email_uses_global_messages_endpoint(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "msg1",
            "subject": "Test",
            "from": {"emailAddress": {"name": "X", "address": "x@y.com"}},
            "receivedDateTime": "2026-04-25",
            "body": {"content": "hello", "contentType": "text"},
            "bodyPreview": "hello",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.read_email("msg-id-xyz")

        called_url = mock_client.get.call_args[0][0]
        # /me/messages/{id} — pas dans un dossier specifique
        assert called_url.endswith("/me/messages/msg-id-xyz")
        assert "mailFolders" not in called_url
