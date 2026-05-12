"""Tests for strip_quoted_text() — coverage of FR/EN Gmail + Outlook patterns."""

from vicsia_email_mcp.text_utils import strip_quoted_text


class TestRFCQuotes:
    """RFC 3676 lines starting with `>` — universal plain-text quote marker."""

    def test_single_level_quote_stripped(self):
        body = "Ma reponse claire.\n\n> Le message precedent\n> sur deux lignes"
        assert strip_quoted_text(body) == "Ma reponse claire."

    def test_multi_level_quotes_stripped(self):
        body = "Ma reponse.\n\n> Reponse niveau 1\n>> Reponse niveau 2\n>>> Original"
        assert strip_quoted_text(body) == "Ma reponse."

    def test_quotes_without_space_after_chevron(self):
        body = "OK.\n>quote sans espace\n>>encore"
        assert strip_quoted_text(body) == "OK."

    def test_no_quotes_returns_unchanged(self):
        body = "Juste du contenu normal.\nSans aucune citation."
        assert strip_quoted_text(body) == body


class TestGmailAttribution:
    """Attribution Gmail — 'On X wrote:' (EN) / 'Le X a écrit :' (FR)."""

    def test_gmail_en_attribution(self):
        body = (
            "Je confirme pour mardi.\n"
            "\n"
            "On May 9, 2026 at 14:30, Jean <jean@example.com> wrote:\n"
            "Salut, on se voit mardi ?"
        )
        assert strip_quoted_text(body) == "Je confirme pour mardi."

    def test_gmail_fr_attribution(self):
        body = (
            "Oui parfait pour 14h.\n"
            "\n"
            "Le 9 mai 2026 a 14:30, Jean <jean@example.com> a écrit :\n"
            "On se voit mardi ?"
        )
        assert strip_quoted_text(body) == "Oui parfait pour 14h."

    def test_attribution_at_start_returns_empty(self):
        """Cas degenere : tout le body est quoted."""
        body = "Le 9 mai 2026, Jean a écrit :\n> contenu cite"
        assert strip_quoted_text(body) == ""


class TestOutlookSeparators:
    """Separateurs Outlook : ____ underscores, -----Original Message-----."""

    def test_outlook_underscores(self):
        body = (
            "Ma reponse.\n"
            "\n"
            "________________________________\n"
            "From: Jean\n"
            "Sent: 9 May 2026\n"
        )
        assert strip_quoted_text(body) == "Ma reponse."

    def test_outlook_original_message_en(self):
        body = (
            "OK c'est bon.\n"
            "\n"
            "-----Original Message-----\n"
            "From: jean@example.com\n"
            "Hello"
        )
        assert strip_quoted_text(body) == "OK c'est bon."

    def test_outlook_message_origine_fr(self):
        body = (
            "Validé.\n"
            "\n"
            "-----Message d'origine-----\n"
            "De : jean@example.com\n"
        )
        assert strip_quoted_text(body) == "Validé."

    def test_outlook_ursprungliche_nachricht_de(self):
        body = (
            "Bestätigt.\n"
            "\n"
            "-----Ursprüngliche Nachricht-----\n"
            "Von: jean@example.com\n"
        )
        assert strip_quoted_text(body) == "Bestätigt."


class TestOutlookHeaderBlock:
    """Outlook produit parfois un bloc From/Sent/To/Subject contigu sans separateur."""

    def test_header_block_en(self):
        body = (
            "Validé pour mardi.\n"
            "\n"
            "From: jean@example.com\n"
            "Sent: Tuesday May 9 2026\n"
            "To: marie@example.com\n"
            "Subject: Re: meeting"
        )
        assert strip_quoted_text(body) == "Validé pour mardi."

    def test_header_block_fr(self):
        body = (
            "OK c'est bon.\n"
            "\n"
            "De : jean@example.com\n"
            "Envoyé : mardi 9 mai 2026\n"
            "À : marie@example.com"
        )
        assert strip_quoted_text(body) == "OK c'est bon."

    def test_single_header_line_not_stripped(self):
        """Un seul From: en debut de ligne ne doit PAS declencher le strip
        (pourrait etre une mention legitime dans le body)."""
        body = "Voici l'extrait :\nFrom: jean@example.com\nC'est lui qu'il faut contacter."
        result = strip_quoted_text(body)
        assert "Voici l'extrait" in result
        assert "C'est lui qu'il faut contacter" in result


class TestMixedPatterns:
    """Cas reels : plusieurs patterns peuvent etre presents — on prend le plus tot."""

    def test_attribution_before_quotes(self):
        body = (
            "Ma reponse.\n"
            "\n"
            "Le 9 mai 2026, Jean a écrit :\n"
            "> Message cite\n"
            "> Sur deux lignes"
        )
        assert strip_quoted_text(body) == "Ma reponse."

    def test_quotes_only_no_attribution(self):
        """Forward style : juste des > sans attribution explicite."""
        body = "OK.\n\n> Premier message\n> Sur plusieurs lignes\n> Cite proprement"
        assert strip_quoted_text(body) == "OK."

    def test_multiple_attributions_uses_earliest(self):
        """Thread imbrique : on coupe au PREMIER marqueur trouve."""
        body = (
            "Ma reponse niveau 2.\n"
            "\n"
            "Le 9 mai 2026, Jean a écrit :\n"
            "> Ma reponse niveau 1\n"
            ">\n"
            "> Le 8 mai 2026, Marie a écrit :\n"
            "> > Message initial"
        )
        result = strip_quoted_text(body)
        assert result == "Ma reponse niveau 2."


class TestEdgeCases:
    """Cas limites : body vide, None-like, juste du blanc."""

    def test_empty_body(self):
        assert strip_quoted_text("") == ""

    def test_whitespace_only(self):
        assert strip_quoted_text("   \n\n   ") == ""

    def test_no_strip_needed_preserves_trailing_whitespace_stripped(self):
        body = "Contenu propre.\n\n"
        # rstrip() retire le \n trailing
        assert strip_quoted_text(body) == "Contenu propre."

    def test_very_long_body_without_quotes(self):
        """Performance test : 10k chars sans quotes — pas de degradation."""
        body = "A" * 10_000
        assert strip_quoted_text(body) == body
