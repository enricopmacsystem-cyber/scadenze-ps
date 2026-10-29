"""Sicurezza applicativa: password hashing, CSRF, rate limit, cifratura secrets."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

# Prefisso hash legacy SHA-256 (pre-hardening)
_LEGACY_SHA256_LEN = 64

# Rate limit login (in-memory per processo)
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 300
_LOGIN_MAX_ATTEMPTS = 8


def hash_password(password: str) -> str:
    """Hash moderno (scrypt via Werkzeug)."""
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash: str, password: str) -> tuple[bool, bool]:
    """
    Verifica password.
    Ritorna (ok, needs_rehash) — needs_rehash True se era SHA-256 legacy.
    """
    if not password_hash:
        return False, False
    # Werkzeug modern hashes start with method$
    if password_hash.startswith(("scrypt:", "pbkdf2:", "argon2:")):
        return check_password_hash(password_hash, password), False
    # Legacy: hex SHA-256 senza salt
    if len(password_hash) == _LEGACY_SHA256_LEN and all(
        c in "0123456789abcdef" for c in password_hash.lower()
    ):
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        ok = hmac.compare_digest(password_hash.lower(), digest.lower())
        return ok, ok  # se ok → rehash al login
    # Fallback werkzeug (altri formati)
    try:
        return check_password_hash(password_hash, password), False
    except (ValueError, TypeError):
        return False, False


def _fernet_key_from_secret(secret: str) -> bytes:
    """Deriva chiave 32 byte url-safe da secret_key app."""
    raw = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_secret(plaintext: str, app_secret: str) -> str:
    """Cifra un secret at-rest. Formato: enc:v1:<token>."""
    if not plaintext:
        return ""
    if plaintext.startswith("enc:v1:"):
        return plaintext
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        # Fallback: non lasciare in chiaro se cryptography manca — rifiuta
        raise RuntimeError(
            "Pacchetto cryptography richiesto per cifrare la password SMTP. "
            "Esegui: pip install cryptography"
        )
    f = Fernet(_fernet_key_from_secret(app_secret))
    token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"enc:v1:{token}"


def decrypt_secret(stored: str, app_secret: str) -> str:
    """Decifra secret; se non cifrato (legacy) restituisce il valore grezzo."""
    if not stored:
        return ""
    if not stored.startswith("enc:v1:"):
        return stored
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("Pacchetto cryptography richiesto per leggere la password SMTP.")
    token = stored[len("enc:v1:") :]
    f = Fernet(_fernet_key_from_secret(app_secret))
    return f.decrypt(token.encode("ascii")).decode("utf-8")


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf(session_token: str | None, form_token: str | None) -> bool:
    if not session_token or not form_token:
        return False
    return hmac.compare_digest(session_token, form_token)


def login_rate_limited(key: str) -> bool:
    """True se troppo tentativi per username/IP."""
    now = time.time()
    window = _login_attempts[key]
    _login_attempts[key] = [t for t in window if now - t < _LOGIN_WINDOW_SEC]
    return len(_login_attempts[key]) >= _LOGIN_MAX_ATTEMPTS


def register_login_failure(key: str) -> None:
    _login_attempts[key].append(time.time())


def clear_login_failures(key: str) -> None:
    _login_attempts.pop(key, None)


def app_secret_key() -> str:
    """Chiave app persistente su NAS (sessioni Flask + cifratura SMTP)."""
    from app.paths import CONFIG_DIR, ensure_dirs

    ensure_dirs()
    key_file = CONFIG_DIR / "secret_key.txt"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


def strong_temp_password() -> str:
    """Password temporanea per reset admin (non prevedibile)."""
    return secrets.token_urlsafe(10)


def password_policy_ok(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "La password deve avere almeno 8 caratteri"
    return True, ""
