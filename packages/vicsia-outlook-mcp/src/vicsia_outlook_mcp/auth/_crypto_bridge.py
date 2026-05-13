"""Bridge to Vicsia's crypto module for token decryption.

Vicsia stocke les tokens OAuth chiffrés via Fernet (clé dérivée du machine ID).
Le subprocess uvx vicsia-outlook-mcp ne peut pas importer src.core.crypto :
Vicsia injecte donc VICSIA_FERNET_KEY dans l'env du subprocess.

Sans VICSIA_FERNET_KEY (mode standalone hors Vicsia), fallback no-op : on suppose
que les tokens sont stockés en plaintext.
"""

import logging
import os

logger = logging.getLogger(__name__)

_KEY = os.environ.get("VICSIA_FERNET_KEY", "")

try:
    from cryptography.fernet import Fernet, InvalidToken

    _fernet: Fernet | None = Fernet(_KEY.encode()) if _KEY else None
except ImportError:
    _fernet = None
    InvalidToken = Exception  # type: ignore[assignment,misc]
except Exception as e:
    logger.warning("VICSIA_FERNET_KEY invalide : %s", type(e).__name__)
    _fernet = None


def is_encrypted(value: str) -> bool:
    """Détecte un ciphertext Fernet (préfixe gAAAAA en base64url)."""
    return bool(value and value.startswith("gAAAAA"))


def decrypt(value: str) -> str:
    """Déchiffre une valeur chiffrée par Vicsia. Renvoie '' si impossible.

    - Pas de fernet (clé manquante / cryptography non installé) → renvoie value tel quel
      (compat plaintext).
    - Valeur non Fernet → renvoie tel quel.
    - Token corrompu / mauvaise clé → renvoie '' (caller doit re-auth).
    """
    if not value:
        return value
    if not is_encrypted(value):
        return value
    if _fernet is None:
        logger.warning("Token chiffré reçu mais VICSIA_FERNET_KEY absente — re-auth requise")
        return ""
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        logger.warning("Décryptage Fernet échoué : token invalide ou clé changée")
        return ""


def encrypt(value: str) -> str:
    """Chiffre une valeur. Renvoie tel quel si pas de clé (mode standalone)."""
    if not value or _fernet is None:
        return value
    return _fernet.encrypt(value.encode()).decode()
