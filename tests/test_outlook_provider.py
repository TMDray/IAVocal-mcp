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


def _make_mock_post_response(returned_id: str):
    """Helper: mock httpx response pour POST avec un id de retour."""
    resp = MagicMock()
    resp.json.return_value = {"id": returned_id}
    resp.raise_for_status = MagicMock()
    return resp


def _make_mock_client(post_response):
    """Helper: mock httpx.AsyncClient context manager."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=post_response)
    return client


class TestCreateDraftReplyPreservesQuote:
    """Bug critique: l'ancienne impl (createReply puis PATCH body) écrasait le
    quote du fil mail. Le fix utilise le 'comment' parameter de createReply qui
    insère le texte au-dessus du quote sans le perdre.
    """

    @pytest.mark.asyncio
    async def test_reply_uses_comment_param_not_patch(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("draft-reply-id")
        mock_client = _make_mock_client(mock_resp)
        # Garde-fou: PATCH ne doit JAMAIS être appelé (sinon on écrase le quote)
        mock_client.patch = AsyncMock(side_effect=AssertionError("PATCH écrase le quote — ne doit pas être appelé"))

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            result = await provider.create_draft("", "", "Ma réponse", reply_to="msg-original-id")

        assert result.id == "draft-reply-id"
        called_url = mock_client.post.call_args[0][0]
        assert called_url.endswith("/me/messages/msg-original-id/createReply")
        # Le body de la requête doit utiliser 'comment' (pas 'body')
        json_payload = mock_client.post.call_args.kwargs["json"]
        assert json_payload == {"comment": "Ma réponse"}, (
            "createReply doit recevoir {'comment': body} pour préserver le quote du fil"
        )


class TestCreateDraftFiltersEmptyRecipients:
    """to='a@b.com, , c@d.com' ne doit pas envoyer un destinataire vide à Graph
    (qui répondrait 400). Filtre les chaînes vides après split.
    """

    @pytest.mark.asyncio
    async def test_empty_recipients_filtered_out(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("draft-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_draft("a@b.com,  ,c@d.com,", "Sujet", "Corps")

        json_payload = mock_client.post.call_args.kwargs["json"]
        recipients = json_payload.get("toRecipients", [])
        addresses = [r["emailAddress"]["address"] for r in recipients]
        assert addresses == ["a@b.com", "c@d.com"], (
            f"Destinataires vides doivent être filtrés. Reçu: {addresses}"
        )


class TestReadEmailUsesPreferTextBody:
    """Bug évité: au lieu d'un strip_html maison fragile (laissait CSS/JS dans
    le body, ne décodait pas les entities exotiques), on délègue à Graph via le
    header Prefer. Graph retourne du texte propre directement.
    """

    @pytest.mark.asyncio
    async def test_read_email_sends_prefer_text_body_header(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "msg1",
            "subject": "Test",
            "from": {"emailAddress": {"name": "X", "address": "x@y.com"}},
            "receivedDateTime": "2026-04-25",
            "body": {"content": "Hello clean text", "contentType": "text"},
            "bodyPreview": "Hello",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {"Authorization": "Bearer X"}))):
            email = await provider.read_email("msg1")

        # Le header Prefer doit être présent, sinon Graph renvoie du HTML
        sent_headers = mock_client.get.call_args.kwargs["headers"]
        assert "Prefer" in sent_headers
        assert 'outlook.body-content-type="text"' in sent_headers["Prefer"]
        # Le body est utilisé brut (plus de strip maison)
        assert email.body == "Hello clean text"


class TestListEventsDirect:
    """Couverture directe de list_events — pas seulement via mock du serveur."""

    @pytest.mark.asyncio
    async def test_list_events_uses_calendarview_endpoint(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"value": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.list_events(7)

        called_url = mock_client.get.call_args[0][0]
        assert called_url.endswith("/me/calendarview"), (
            "list_events doit utiliser /me/calendarview (qui expand les recurrences) "
            "et non /me/events (qui retourne les masters de série non-expandées)"
        )

    @pytest.mark.asyncio
    async def test_list_events_parses_full_response(self):
        """Vérifie le parsing : title, start, end, location, attendees."""
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [
                {
                    "id": "ev1",
                    "subject": "Standup",
                    "start": {"dateTime": "2026-05-09T09:00:00", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-05-09T09:30:00", "timeZone": "UTC"},
                    "location": {"displayName": "Salle 3"},
                    "bodyPreview": "Daily standup",
                    "attendees": [
                        {"emailAddress": {"address": "a@x.com"}},
                        {"emailAddress": {"address": "b@x.com"}},
                    ],
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            events = await provider.list_events(7)

        assert len(events) == 1
        ev = events[0]
        assert ev.id == "ev1"
        assert ev.title == "Standup"
        assert ev.start == "2026-05-09T09:00:00"
        assert ev.end == "2026-05-09T09:30:00"
        assert ev.location == "Salle 3"
        assert ev.attendees == ["a@x.com", "b@x.com"]

    @pytest.mark.asyncio
    async def test_list_events_handles_missing_optional_fields(self):
        """Événement sans location ni attendees — ne doit pas crasher."""
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "value": [
                {
                    "id": "ev2",
                    "subject": "Solo",
                    "start": {"dateTime": "2026-05-09T10:00:00"},
                    "end": {"dateTime": "2026-05-09T11:00:00"},
                    # pas de location, pas d'attendees
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            events = await provider.list_events(7)

        assert events[0].location == ""
        assert events[0].attendees == []


class TestCreateDraftNewEmail:
    """Couverture directe création d'un nouveau draft (pas reply)."""

    @pytest.mark.asyncio
    async def test_new_draft_with_single_recipient(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("draft-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            result = await provider.create_draft("user@example.com", "Sujet", "Corps du mail")

        assert result.id == "draft-id"
        called_url = mock_client.post.call_args[0][0]
        assert called_url.endswith("/me/messages")  # nouveau draft, pas /createReply

        json_payload = mock_client.post.call_args.kwargs["json"]
        assert json_payload["subject"] == "Sujet"
        assert json_payload["body"] == {"contentType": "text", "content": "Corps du mail"}
        assert json_payload["toRecipients"] == [
            {"emailAddress": {"address": "user@example.com"}}
        ]

    @pytest.mark.asyncio
    async def test_new_draft_with_multiple_recipients(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("draft-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_draft("a@x.com,b@x.com,c@x.com", "Multi", "Body")

        json_payload = mock_client.post.call_args.kwargs["json"]
        addresses = [r["emailAddress"]["address"] for r in json_payload["toRecipients"]]
        assert addresses == ["a@x.com", "b@x.com", "c@x.com"]


class TestCreateEventWithDescription:
    """create_event avec description doit ajouter le body au payload."""

    @pytest.mark.asyncio
    async def test_description_added_as_body(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("event-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event(
                "Meeting",
                "2026-05-09T14:00:00Z",
                "2026-05-09T15:00:00Z",
                description="Agenda du sprint",
            )

        json_payload = mock_client.post.call_args.kwargs["json"]
        assert json_payload["body"] == {"contentType": "text", "content": "Agenda du sprint"}

    @pytest.mark.asyncio
    async def test_no_description_omits_body(self):
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("event-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event("Meeting", "2026-05-09T14:00:00Z", "2026-05-09T15:00:00Z")

        json_payload = mock_client.post.call_args.kwargs["json"]
        assert "body" not in json_payload


class TestCreateEventTimezoneHandling:
    """Bug critique: ancien code envoyait timeZone='UTC' avec un dateTime contenant
    déjà un offset → double conversion non-déterministe → RDV à la mauvaise heure.

    Doc MS: dateTimeTimeZone exige cohérence entre dateTime et timeZone.
    Fix: si offset présent → convertir en UTC. Sinon → utiliser VICSIA_USER_TZ.
    """

    @pytest.mark.asyncio
    async def test_offset_in_start_converted_to_utc(self):
        """start='2026-05-09T14:00:00+02:00' → dateTime='2026-05-09T12:00:00' tz='UTC'."""
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        mock_resp = _make_mock_post_response("event-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event(
                "Meeting",
                "2026-05-09T14:00:00+02:00",
                "2026-05-09T15:00:00+02:00",
            )

        json_payload = mock_client.post.call_args.kwargs["json"]
        # 14h Paris (+02:00) = 12h UTC
        assert json_payload["start"] == {"dateTime": "2026-05-09T12:00:00", "timeZone": "UTC"}
        assert json_payload["end"] == {"dateTime": "2026-05-09T13:00:00", "timeZone": "UTC"}

    @pytest.mark.asyncio
    async def test_no_offset_uses_user_timezone_env(self, monkeypatch):
        """start='2026-05-09T14:00:00' (sans offset) + VICSIA_USER_TZ='Europe/Paris'
        → dateTime tel quel + timeZone='Europe/Paris'.
        """
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        monkeypatch.setenv("VICSIA_USER_TZ", "Europe/Paris")

        mock_resp = _make_mock_post_response("event-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event(
                "Meeting",
                "2026-05-09T14:00:00",
                "2026-05-09T15:00:00",
            )

        json_payload = mock_client.post.call_args.kwargs["json"]
        assert json_payload["start"] == {"dateTime": "2026-05-09T14:00:00", "timeZone": "Europe/Paris"}
        assert json_payload["end"] == {"dateTime": "2026-05-09T15:00:00", "timeZone": "Europe/Paris"}

    @pytest.mark.asyncio
    async def test_no_offset_no_env_defaults_utc(self, monkeypatch):
        """Sans offset ET sans VICSIA_USER_TZ → fallback UTC (rétrocompat)."""
        from vicsia_email_mcp.providers.outlook import OutlookProvider

        monkeypatch.delenv("VICSIA_USER_TZ", raising=False)

        mock_resp = _make_mock_post_response("event-id")
        mock_client = _make_mock_client(mock_resp)

        provider = OutlookProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event(
                "Meeting",
                "2026-05-09T14:00:00",
                "2026-05-09T15:00:00",
            )

        json_payload = mock_client.post.call_args.kwargs["json"]
        assert json_payload["start"] == {"dateTime": "2026-05-09T14:00:00", "timeZone": "UTC"}
