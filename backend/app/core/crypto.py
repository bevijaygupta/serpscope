"""Symmetric encryption for stored integration credentials."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _key() -> bytes:
    """Use a dedicated credential key when configured, otherwise the legacy secret."""
    material = settings.credential_encryption_key or settings.secret_key
    return base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())


def encrypt(secret: str) -> str:
    return Fernet(_key()).encrypt(secret.encode()).decode()


def decrypt(token: str) -> str:
    return Fernet(_key()).decrypt(token.encode()).decode()
