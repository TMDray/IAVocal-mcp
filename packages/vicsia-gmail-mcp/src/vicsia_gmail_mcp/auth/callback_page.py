"""OAuth callback HTML pages for vicsia-gmail-mcp.

Clean, branded pages shown to the user after OAuth authorization.
Design aligned with Vicsia v3 (gradient bg, soft shadows, orange accent).
"""

# Template Python: tous les % CSS doivent etre echappes %%, seuls les %s sont
# substitues. Texte sans accents (convention projet).
_BASE_STYLE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #1a1a1a;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 2rem;
    background: linear-gradient(145deg, #fff7ed 0%%, #fef9f6 55%%, #f3f4f6 100%%);
}
.card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 2.75rem 2.5rem;
    max-width: 440px;
    width: 100%%;
    text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04);
}
.brand {
    margin-bottom: 1.5rem;
    font-size: 1.05rem;
    font-weight: 600;
    color: #1a1a1a;
    letter-spacing: -0.01em;
}
.icon {
    width: 72px;
    height: 72px;
    border-radius: 50%%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 1.25rem;
}
h1 {
    font-size: 1.4rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    color: #1a1a1a;
}
.account { color: #6b7280; font-size: 0.9rem; margin-bottom: 0.5rem; font-weight: 500; }
.message { color: #6b7280; font-size: 0.95rem; line-height: 1.55; margin-bottom: 1.75rem; }
.provider { color: #f97316; font-weight: 600; }
.error-detail { color: #dc2626; font-size: 0.85rem; margin-bottom: 1.5rem; word-break: break-word; }
.btn {
    width: 100%%;
    height: 44px;
    border-radius: 8px;
    background: #f97316;
    color: #fff;
    border: none;
    font-size: 0.925rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
}
.btn:hover { opacity: 0.92; }
@media (prefers-color-scheme: dark) {
    body {
        color: #f3f4f6;
        background: linear-gradient(145deg, #0f172a 0%%, #111827 55%%, #1a1208 100%%);
    }
    .card {
        background: #1f2937;
        border-color: #374151;
        box-shadow: 0 8px 32px rgba(0,0,0,0.35);
    }
    .brand, h1 { color: #f3f4f6; }
    .account, .message { color: #9ca3af; }
}
"""

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vicsia - Connexion reussie</title>
    <style>""" + _BASE_STYLE + """
        .icon { background: #f0fdf4; color: #16a34a; }
        @media (prefers-color-scheme: dark) { .icon { background: #14532d; } }
    </style>
</head>
<body>
    <div class="card">
        <div class="brand">Vicsia Desktop</div>
        <div class="icon">
            <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
        </div>
        <h1>Connexion reussie</h1>
        <p class="account">%s</p>
        <p class="message">
            Votre compte <span class="provider">%s</span> est connecte a Vicsia.<br>
            Vous pouvez fermer cet onglet.
        </p>
        <button type="button" class="btn" onclick="try{window.close()}catch(e){}">Fermer cet onglet</button>
    </div>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vicsia - Erreur de connexion</title>
    <style>""" + _BASE_STYLE + """
        .icon { background: #fef2f2; color: #dc2626; }
        @media (prefers-color-scheme: dark) { .icon { background: #451a1a; } }
    </style>
</head>
<body>
    <div class="card">
        <div class="brand">Vicsia Desktop</div>
        <div class="icon">
            <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </div>
        <h1>Erreur de connexion</h1>
        <p class="message">La connexion a echoue. Reessayez depuis Vicsia.</p>
        <p class="error-detail">%s</p>
        <button type="button" class="btn" onclick="try{window.close()}catch(e){}">Fermer cet onglet</button>
    </div>
</body>
</html>"""


def success_page(account: str = "", provider: str = "Gmail") -> str:
    """Generate the success callback page HTML."""
    import html
    return SUCCESS_HTML % (html.escape(account), html.escape(provider))


def error_page(error: str = "") -> str:
    """Generate the error callback page HTML."""
    import html
    return ERROR_HTML % (html.escape(error))
