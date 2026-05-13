"""OAuth callback HTML pages for vicsia-gmail-mcp.

Clean, branded pages shown to the user after OAuth authorization.
"""

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vicsia — Connexion reussie</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #faf9f7;
            color: #2d2d2d;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .card {
            background: #fff;
            border: 1px solid #e8e5e0;
            border-radius: 16px;
            padding: 3rem 2.5rem;
            max-width: 420px;
            width: 90%%;
            text-align: center;
            box-shadow: 0 4px 24px rgba(0,0,0,0.06);
        }
        .icon {
            width: 64px;
            height: 64px;
            background: #f0faf0;
            border: 2px solid #34a853;
            border-radius: 50%%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 1.5rem;
            font-size: 28px;
        }
        h1 {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        .provider {
            color: #e67e22;
            font-weight: 600;
        }
        .account {
            color: #888;
            font-size: 0.9rem;
            margin-top: 0.3rem;
        }
        .message {
            color: #666;
            font-size: 0.95rem;
            margin-top: 1rem;
            line-height: 1.5;
        }
        .close-hint {
            color: #aaa;
            font-size: 0.8rem;
            margin-top: 1.5rem;
        }
        .btn {
            display: inline-block;
            margin-top: 1.5rem;
            padding: 0.6rem 1.8rem;
            background: #e67e22;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            cursor: pointer;
            text-decoration: none;
        }
        .btn:hover { background: #d35400; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">&#10003;</div>
        <h1>Connexion reussie</h1>
        <p class="account">%s</p>
        <p class="message">
            Votre compte <span class="provider">%s</span> est connecte a Vicsia.<br>
            Vous pouvez utiliser vos agents email.
        </p>
        <button class="btn" onclick="window.close()">Fermer</button>
        <p class="close-hint">Cet onglet se fermera automatiquement.</p>
    </div>
    <script>setTimeout(function(){ window.close(); }, 8000);</script>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vicsia — Erreur de connexion</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #faf9f7;
            color: #2d2d2d;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .card {
            background: #fff;
            border: 1px solid #e8e5e0;
            border-radius: 16px;
            padding: 3rem 2.5rem;
            max-width: 420px;
            width: 90%%;
            text-align: center;
            box-shadow: 0 4px 24px rgba(0,0,0,0.06);
        }
        .icon {
            width: 64px;
            height: 64px;
            background: #fef2f2;
            border: 2px solid #e74c3c;
            border-radius: 50%%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 1.5rem;
            font-size: 28px;
        }
        h1 { font-size: 1.3rem; font-weight: 600; margin-bottom: 0.5rem; }
        .message { color: #666; font-size: 0.95rem; margin-top: 1rem; line-height: 1.5; }
        .error-detail { color: #e74c3c; font-size: 0.85rem; margin-top: 0.8rem; }
        .btn {
            display: inline-block;
            margin-top: 1.5rem;
            padding: 0.6rem 1.8rem;
            background: #e67e22;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            cursor: pointer;
        }
        .btn:hover { background: #d35400; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">&#10007;</div>
        <h1>Erreur de connexion</h1>
        <p class="message">La connexion a echoue. Reessayez depuis Vicsia.</p>
        <p class="error-detail">%s</p>
        <button class="btn" onclick="window.close()">Fermer</button>
    </div>
</body>
</html>"""


def success_page(account: str = "", provider: str = "Email") -> str:
    """Generate the success callback page HTML."""
    import html
    return SUCCESS_HTML % (html.escape(account), html.escape(provider))


def error_page(error: str = "") -> str:
    """Generate the error callback page HTML."""
    import html
    return ERROR_HTML % (html.escape(error))
