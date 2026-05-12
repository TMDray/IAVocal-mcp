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
            mock_gmail_provider.search_emails.assert_called_once_with("test", 30)


class TestReadEmail:
    @pytest.mark.asyncio
    async def test_returns_full_content(self, mock_gmail_provider):
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import read_email
            result = await read_email("msg1")
            assert "jean@test.com" in result
            assert "Reunion" in result
            assert "Je confirme la reunion" in result

    @pytest.mark.asyncio
    async def test_strip_quotes_false_by_default(self, mock_gmail_provider):
        """Comportement par defaut inchange — les quotes sont presentes."""
        body_with_quotes = "Ma reponse.\n\nLe 9 mai, Jean a écrit :\n> Message initial"
        mock_gmail_provider.read_email.return_value = AsyncMock(
            id="msg1", subject="Re: test", sender="a@t.com", date="2026-05-11",
            snippet="", body=body_with_quotes,
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import read_email
            result = await read_email("msg1")
        assert "Le 9 mai, Jean a écrit :" in result
        assert "Message initial" in result

    @pytest.mark.asyncio
    async def test_strip_quotes_true_removes_history(self, mock_gmail_provider):
        """strip_quotes=True retire la chaine de reponses, garde le nouveau contenu."""
        body_with_quotes = "Ma reponse.\n\nLe 9 mai, Jean a écrit :\n> Message initial"
        mock_gmail_provider.read_email.return_value = AsyncMock(
            id="msg1", subject="Re: test", sender="a@t.com", date="2026-05-11",
            snippet="", body=body_with_quotes,
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import read_email
            result = await read_email("msg1", strip_quotes=True)
        assert "Ma reponse." in result
        assert "Le 9 mai, Jean a écrit :" not in result
        assert "Message initial" not in result


class TestPreviewEmails:
    @pytest.mark.asyncio
    async def test_returns_preview_for_each_id(self, mock_gmail_provider):
        mock_gmail_provider.read_email.return_value = AsyncMock(
            id="msg1", subject="Reunion", sender="jean@test.com",
            date="2026-05-11", snippet="", body="Bonjour, je confirme la reunion de mardi.",
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import preview_emails
            result = await preview_emails(["msg1"])
        assert "Reunion" in result
        assert "jean@test.com" in result
        assert "je confirme la reunion" in result
        assert "msg1" in result

    @pytest.mark.asyncio
    async def test_capped_at_10_ids(self, mock_gmail_provider):
        mock_gmail_provider.read_email.return_value = AsyncMock(
            id="x", subject="S", sender="a@t.com", date="2026-05-11",
            snippet="", body="Contenu.",
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import preview_emails
            await preview_emails([f"id{i}" for i in range(15)])
        assert mock_gmail_provider.read_email.call_count == 10

    @pytest.mark.asyncio
    async def test_body_truncated_at_400_chars(self, mock_gmail_provider):
        long_body = "A" * 600
        mock_gmail_provider.read_email.return_value = AsyncMock(
            id="msg1", subject="Long", sender="a@t.com", date="2026-05-11",
            snippet="", body=long_body,
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import preview_emails
            result = await preview_emails(["msg1"])
        assert result.count("A") == 400
        assert "…" in result

    @pytest.mark.asyncio
    async def test_quotes_stripped_automatically(self, mock_gmail_provider):
        body = "Nouveau contenu.\n\nLe 9 mai, Jean a écrit :\n> Ancien message"
        mock_gmail_provider.read_email.return_value = AsyncMock(
            id="msg1", subject="Re: test", sender="a@t.com", date="2026-05-11",
            snippet="", body=body,
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import preview_emails
            result = await preview_emails(["msg1"])
        assert "Nouveau contenu." in result
        assert "Ancien message" not in result

    @pytest.mark.asyncio
    async def test_failed_id_does_not_crash_others(self, mock_gmail_provider):
        """Un ID invalide produit un message d'erreur mais n'interrompt pas les autres."""
        import httpx
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_gmail_provider.read_email.side_effect = [
            httpx.HTTPStatusError("Not found", request=AsyncMock(spec=httpx.Request), response=mock_response),
            AsyncMock(id="msg2", subject="OK", sender="b@t.com", date="2026-05-11",
                      snippet="", body="Contenu valide."),
        ]
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import preview_emails
            result = await preview_emails(["bad_id", "msg2"])
        assert "erreur" in result
        assert "Contenu valide." in result


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


# ==================== Robustness tests (Phase 2 — diagnose real crash causes) ====================


class TestRobustnessSearchHugeSnippets:
    """Provider renvoie 20 mails avec snippets enormes (2000 chars chacun).

    Verifie que la sortie est bornee grace au [:150] dans server.py — sinon
    20 × 2000 = 40 000 chars de body retournes = risque saturation contexte LLM.
    """

    @pytest.mark.asyncio
    async def test_snippets_truncated_to_150_chars(self, mock_gmail_provider):
        huge = "x" * 2000
        mock_gmail_provider.search_emails.return_value = [
            Email(id=f"m{i}", subject=f"S{i}", sender=f"a{i}@t.com", date="2026-05-11", snippet=huge)
            for i in range(20)
        ]
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            result = await search_emails("test", 20)

        # Chaque ligne "Apercu: ..." doit etre bornee par 150 chars de body + le prefixe
        # On verifie que le body total des apercus tient dans 150 * 20 = 3000 chars
        # (et pas 2000 * 20 = 40000 chars)
        # On compte les "x" presents — il devrait y en avoir au max 150 * 20 = 3000
        x_count = result.count("x")
        assert x_count <= 150 * 20, (
            f"Snippets non tronques: {x_count} 'x' dans la sortie "
            f"(attendu <= 3000). Risque saturation contexte."
        )


class TestRobustnessReadEmailHugeBody:
    """read_email avec un corps de 50 KB.

    Documente le comportement ACTUEL : aucune troncature → tout le body
    est retourne. Si ce test passe avec 50 KB sans crash, on sait que le
    point de saturation est plus loin (cote LLM, pas cote MCP).
    """

    @pytest.mark.asyncio
    async def test_50kb_body_returned_in_full(self, mock_gmail_provider):
        huge_body = "A" * 50_000
        mock_gmail_provider.read_email.return_value = Email(
            id="big",
            subject="Newsletter",
            sender="news@test.com",
            date="2026-05-11",
            snippet="preview",
            body=huge_body,
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import read_email
            result = await read_email("big")

        assert len(result) >= 50_000, (
            "read_email tronque deja le body — verifier si c'est intentionnel"
        )
        assert result.count("A") >= 50_000


class TestRobustnessProviderHTTP500:
    """Provider leve httpx.HTTPStatusError 500 (erreur serveur Gmail/Graph).

    Comportement attendu : exception propre qui remonte vers FastMCP,
    pas un crash du process MCP.
    """

    @pytest.mark.asyncio
    async def test_500_propagates_cleanly(self, mock_gmail_provider):
        import httpx
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_gmail_provider.search_emails.side_effect = httpx.HTTPStatusError(
            "Server error", request=AsyncMock(spec=httpx.Request), response=mock_response
        )

        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            with pytest.raises(httpx.HTTPStatusError):
                await search_emails("test", 10)


class TestRobustnessProvider401Expired:
    """Provider leve une erreur d'authentification (token expire).

    Comportement attendu : exception identifiable, pas un crash silencieux
    avec un Bearer invalide qui partirait en boucle.
    """

    @pytest.mark.asyncio
    async def test_401_propagates_with_clear_message(self, mock_gmail_provider):
        import httpx
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_gmail_provider.search_emails.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=AsyncMock(spec=httpx.Request), response=mock_response
        )

        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await search_emails("test", 10)
            assert exc_info.value.response.status_code == 401

    @pytest.mark.asyncio
    async def test_runtime_error_not_authenticated(self, mock_gmail_provider):
        """Cas RuntimeError 'Google not authenticated' lance par le provider."""
        mock_gmail_provider.search_emails.side_effect = RuntimeError(
            "Google not authenticated — connect via Vicsia Connexions page"
        )

        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            with pytest.raises(RuntimeError, match="not authenticated"):
                await search_emails("test", 10)


class TestRobustnessMalformedResponse:
    """Provider renvoie des Email avec champs manquants/vides.

    Cas reels :
    - sender vide (ex: mail systeme sans From propre)
    - subject None ou vide
    - snippet absent / None
    - date au mauvais format
    """

    @pytest.mark.asyncio
    async def test_empty_fields_dont_crash(self, mock_gmail_provider):
        mock_gmail_provider.search_emails.return_value = [
            Email(id="ok", subject="", sender="", date="", snippet=""),
            Email(id="partial", subject="Hi", sender="x@y.com", date="", snippet=""),
        ]
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            result = await search_emails("test", 10)

        assert "ok" in result
        assert "partial" in result

    @pytest.mark.asyncio
    async def test_read_email_with_none_body(self, mock_gmail_provider):
        """Body None doit etre gere — actuellement le format string ferait 'None'."""
        mock_gmail_provider.read_email.return_value = Email(
            id="no_body", subject="Vide", sender="x@y.com", date="2026-05-11",
            snippet="", body=None
        )
        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import read_email
            result = await read_email("no_body")
        # Doit pas crasher — verifie juste qu'on a quelque chose de propre
        assert "Vide" in result


class TestRobustnessConcurrentCalls:
    """Deux search_emails appeles en parallele.

    Verifie qu'il n'y a pas de race condition sur le singleton _provider
    ni de melange de resultats entre les deux appels.
    """

    @pytest.mark.asyncio
    async def test_two_concurrent_searches(self, mock_gmail_provider):
        import asyncio

        call_count = {"n": 0}

        async def search_with_delay(query, max_results):
            call_count["n"] += 1
            await asyncio.sleep(0.01)
            return [
                Email(id=f"{query}_1", subject=f"Result for {query}",
                      sender="a@t.com", date="2026-05-11", snippet=f"snippet {query}")
            ]

        mock_gmail_provider.search_emails.side_effect = search_with_delay

        with patch("vicsia_email_mcp.server.get_provider", return_value=mock_gmail_provider):
            from vicsia_email_mcp.server import search_emails
            r1, r2 = await asyncio.gather(
                search_emails("alpha", 10),
                search_emails("beta", 10),
            )

        assert "Result for alpha" in r1
        assert "Result for beta" in r2
        assert "Result for beta" not in r1
        assert "Result for alpha" not in r2
        assert call_count["n"] == 2
