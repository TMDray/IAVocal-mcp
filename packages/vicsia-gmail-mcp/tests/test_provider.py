"""Tests for GmailProvider — verify Gmail API endpoints, params, body decoding.

Bugs critiques corrigés (0.1.8) qu'on garde-foute ici :
- search_emails sans labelIds=INBOX → couvrait toute la mailbox (drafts, sent)
- read_email ne décodait que text/plain → emails html-only (60-80% du flux) → snippet
- create_draft reply confondait id Gmail et Message-ID header → thread cassé
- create_event sans timeZone fallback → RDV à la mauvaise heure si LLM omet l'offset
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_response(json_payload: dict, status: int = 200):
    resp = MagicMock()
    resp.json.return_value = json_payload
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


def _make_mock_client(*, get_responses=None, post_responses=None):
    """Mock httpx.AsyncClient avec side_effect pour GET/POST séquentiels."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    if get_responses is not None:
        client.get = AsyncMock(side_effect=get_responses)
    if post_responses is not None:
        client.post = AsyncMock(side_effect=post_responses)
    return client


def _b64url(s: str) -> str:
    """Encode UTF-8 string in base64url for Gmail payload data."""
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


class TestSearchEmailsScopedToInbox:
    """search_emails doit passer labelIds=INBOX. Sans ça, /messages couvre TOUTES
    les boîtes (Sent, Drafts, Spam, Trash) et les drafts maison remontent.
    Bug analogue à Outlook 0.1.4.
    """

    @pytest.mark.asyncio
    async def test_search_passes_labelids_inbox(self):
        from vicsia_gmail_mcp.provider import GmailProvider

        # 1 list (vide) — pas de get individuel à mocker
        list_resp = _make_mock_response({"messages": []})
        mock_client = _make_mock_client(get_responses=[list_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.search_emails("test", 5)

        # Premier appel GET = list — vérifier params
        first_call = mock_client.get.call_args_list[0]
        params = first_call.kwargs["params"]
        assert params.get("labelIds") == "INBOX", (
            "search_emails doit scoper INBOX. Sans labelIds, la recherche couvre "
            f"toute la mailbox. Reçu: {params}"
        )

    @pytest.mark.asyncio
    async def test_search_handles_empty_mailbox(self):
        """Réponse Gmail sans 'messages' → retourne [] sans crash."""
        from vicsia_gmail_mcp.provider import GmailProvider

        list_resp = _make_mock_response({})  # pas de clé 'messages'
        mock_client = _make_mock_client(get_responses=[list_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            results = await provider.search_emails("rien", 10)

        assert results == []


class TestReadEmailDecodesHtml:
    """Bug critique: 60-80% des emails (newsletters, transactionnels) sont
    text/html only. Sans décodage côté client, on retombait sur snippet ~150 char.
    """

    @pytest.mark.asyncio
    async def test_html_only_email_decoded_to_text(self):
        from vicsia_gmail_mcp.provider import GmailProvider

        html = "<html><body><p>Bonjour,</p><p>Voici votre <b>facture</b>.</p></body></html>"
        msg_resp = _make_mock_response({
            "id": "msg1",
            "snippet": "Bonjour, Voici votre fact...",
            "payload": {
                "mimeType": "text/html",
                "headers": [{"name": "From", "value": "n@x.com"}, {"name": "Subject", "value": "X"}, {"name": "Date", "value": "D"}],
                "body": {"data": _b64url(html)},
            },
        })
        mock_client = _make_mock_client(get_responses=[msg_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            email = await provider.read_email("msg1")

        # Pas de balises HTML dans le résultat
        assert "<" not in email.body
        assert ">" not in email.body
        # Contenu texte préservé
        assert "Bonjour" in email.body
        assert "facture" in email.body
        # Pas le snippet tronqué
        assert email.body != email.snippet

    @pytest.mark.asyncio
    async def test_html_strips_style_and_script_content(self):
        """Newsletters marketing avec <style> intégré ne doivent pas leak le CSS."""
        from vicsia_gmail_mcp.provider import GmailProvider

        html = "<html><head><style>body{color:red}</style></head><body>Hello</body></html>"
        msg_resp = _make_mock_response({
            "id": "msg1",
            "snippet": "...",
            "payload": {
                "mimeType": "text/html",
                "headers": [],
                "body": {"data": _b64url(html)},
            },
        })
        mock_client = _make_mock_client(get_responses=[msg_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            email = await provider.read_email("msg1")

        assert "color" not in email.body
        assert "red" not in email.body
        assert "Hello" in email.body

    @pytest.mark.asyncio
    async def test_multipart_alternative_prefers_plain_over_html(self):
        """Si plain ET html existent (multipart/alternative), prendre plain."""
        from vicsia_gmail_mcp.provider import GmailProvider

        msg_resp = _make_mock_response({
            "id": "msg1",
            "snippet": "...",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64url("Plain version clean")}},
                    {"mimeType": "text/html", "body": {"data": _b64url("<p>HTML version <b>noise</b></p>")}},
                ],
            },
        })
        mock_client = _make_mock_client(get_responses=[msg_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            email = await provider.read_email("msg1")

        assert "Plain version clean" in email.body
        assert "HTML version" not in email.body


class TestCreateDraftReplyResolvesThread:
    """Bug critique: l'ancienne impl utilisait reply_to (id Gmail interne) à la
    fois comme threadId ET comme valeur de In-Reply-To/References (qui devraient
    être le header Message-ID MIME, pas l'id Gmail).

    Conséquences: thread cassé côté Gmail (400 Bad Request) ET côté destinataire
    (le client mail ne raccroche pas le fil de conversation).

    Le fix fait un GET metadata d'abord pour résoudre les vrais threadId et
    Message-ID header.
    """

    @pytest.mark.asyncio
    async def test_reply_resolves_threadid_and_message_id_header(self):
        from vicsia_gmail_mcp.provider import GmailProvider

        # 1er GET: metadata du message à reply
        meta_resp = _make_mock_response({
            "id": "msg-internal-id",
            "threadId": "thread-abc-123",
            "payload": {
                "headers": [
                    {"name": "Message-ID", "value": "<CABx12345@mail.gmail.com>"},
                    {"name": "Subject", "value": "Question importante"},
                    {"name": "References", "value": "<earlier@mail.gmail.com>"},
                ]
            },
        })
        # 2eme call: POST drafts
        post_resp = _make_mock_response({"id": "draft-new-id"})

        mock_client = _make_mock_client(
            get_responses=[meta_resp],
            post_responses=[post_resp],
        )

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            result = await provider.create_draft("", "", "Ma réponse", reply_to="msg-internal-id")

        assert result.id == "draft-new-id"

        # GET metadata appelé en premier
        assert mock_client.get.call_count == 1
        # POST drafts ensuite
        assert mock_client.post.call_count == 1

        # threadId du draft = celui de la metadata (PAS reply_to)
        post_payload = mock_client.post.call_args.kwargs["json"]
        assert post_payload["message"]["threadId"] == "thread-abc-123"

        # Le MIME raw doit contenir In-Reply-To = Message-ID header
        raw_b64 = post_payload["message"]["raw"]
        raw = base64.urlsafe_b64decode(raw_b64).decode("utf-8")
        assert "In-Reply-To: <CABx12345@mail.gmail.com>" in raw
        # References = anciennes refs + Message-ID
        assert "<earlier@mail.gmail.com>" in raw
        assert "<CABx12345@mail.gmail.com>" in raw

    @pytest.mark.asyncio
    async def test_reply_auto_subject_re_prefix_if_missing(self):
        """Si subject vide, on prend l'orig en ajoutant 'Re: ' si pas déjà présent."""
        from vicsia_gmail_mcp.provider import GmailProvider

        meta_resp = _make_mock_response({
            "id": "msg1",
            "threadId": "thread1",
            "payload": {
                "headers": [
                    {"name": "Message-ID", "value": "<x@m.com>"},
                    {"name": "Subject", "value": "Ma question"},
                ]
            },
        })
        post_resp = _make_mock_response({"id": "draft1"})

        mock_client = _make_mock_client(
            get_responses=[meta_resp],
            post_responses=[post_resp],
        )

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_draft("", "", "OK", reply_to="msg1")

        post_payload = mock_client.post.call_args.kwargs["json"]
        raw = base64.urlsafe_b64decode(post_payload["message"]["raw"]).decode("utf-8")
        assert "Subject: Re: Ma question" in raw


class TestCreateEventTimezone:
    """Bug latent (analogue Outlook 0.1.6): create_event sans timeZone fallback
    laissait Google interpréter le datetime en TZ du calendrier (souvent ≠ TZ user).
    """

    @pytest.mark.asyncio
    async def test_offset_in_start_preserved(self):
        """start='2026-05-09T14:00:00+02:00' → on garde l'offset (Google le respecte).
        On n'ajoute PAS timeZone (sinon double-conversion).
        """
        from vicsia_gmail_mcp.provider import GmailProvider

        post_resp = _make_mock_response({"id": "ev1"})
        mock_client = _make_mock_client(post_responses=[post_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event(
                "Meeting",
                "2026-05-09T14:00:00+02:00",
                "2026-05-09T15:00:00+02:00",
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["start"] == {"dateTime": "2026-05-09T14:00:00+02:00"}
        assert "timeZone" not in payload["start"]
        assert payload["end"] == {"dateTime": "2026-05-09T15:00:00+02:00"}

    @pytest.mark.asyncio
    async def test_no_offset_adds_user_timezone(self, monkeypatch):
        """start sans offset + VICSIA_USER_TZ='Europe/Paris' → timeZone ajouté."""
        from vicsia_gmail_mcp.provider import GmailProvider

        monkeypatch.setenv("VICSIA_USER_TZ", "Europe/Paris")

        post_resp = _make_mock_response({"id": "ev1"})
        mock_client = _make_mock_client(post_responses=[post_resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            await provider.create_event(
                "Meeting",
                "2026-05-09T14:00:00",
                "2026-05-09T15:00:00",
            )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["start"] == {"dateTime": "2026-05-09T14:00:00", "timeZone": "Europe/Paris"}


class TestListEventsHandlesAllDay:
    """Événement all-day → 'date' au lieu de 'dateTime' dans la réponse Google."""

    @pytest.mark.asyncio
    async def test_all_day_event_uses_date_field(self):
        from vicsia_gmail_mcp.provider import GmailProvider

        resp = _make_mock_response({
            "items": [
                {
                    "id": "ev-allday",
                    "summary": "Anniversaire",
                    "start": {"date": "2026-05-10"},  # pas de dateTime → all-day
                    "end": {"date": "2026-05-11"},
                }
            ]
        })
        mock_client = _make_mock_client(get_responses=[resp])

        provider = GmailProvider()
        with patch.object(provider, "_get_client", AsyncMock(return_value=(mock_client, {}))):
            events = await provider.list_events(7)

        assert len(events) == 1
        assert events[0].title == "Anniversaire"
        assert events[0].start == "2026-05-10"
        assert events[0].end == "2026-05-11"
