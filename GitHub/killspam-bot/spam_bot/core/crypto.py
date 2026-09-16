"""Encrypt BYOK Gemini keys at rest (Fernet). KEY_ENCRYPTION_SECRET is a Fernet key:
generate with  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" """
import logging
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet():
    secret = os.getenv("KEY_ENCRYPTION_SECRET")
    if not secret:
        return None
    try:
        return Fernet(secret.encode() if isinstance(secret, str) else secret)
    except Exception as e:
        logging.error(f"Invalid KEY_ENCRYPTION_SECRET: {e}")
        return None


def available() -> bool:
    return _fernet() is not None


def encrypt(plaintext: str):
    f = _fernet()
    if not f or not plaintext:
        return None
    return f.encrypt(plaintext.encode()).decode()


def decrypt(token: str):
    f = _fernet()
    if not f or not token:
        return None
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        logging.error("Failed to decrypt stored key (InvalidToken)")
        return None
