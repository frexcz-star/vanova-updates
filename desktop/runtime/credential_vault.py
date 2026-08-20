"""Encrypt sensitive integration credentials at rest (Phase 4)."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .install_secrets import get_encryption_key_foundation

_ENCRYPT_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    foundation = get_encryption_key_foundation()
    if not foundation:
        raise RuntimeError("encryptionKeyFoundation missing — run ensure_install_secrets()")
    key = base64.urlsafe_b64encode(hashlib.sha256(foundation.encode("utf-8")).digest())
    return Fernet(key)


def is_encrypted(value: str) -> bool:
    return bool(value) and str(value).startswith(_ENCRYPT_PREFIX)


def encrypt_value(plain: str) -> str:
    text = (plain or "").strip()
    if not text:
        return ""
    if is_encrypted(text):
        return text
    token = _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return f"{_ENCRYPT_PREFIX}{token}"


def decrypt_value(stored: str) -> str:
    text = (stored or "").strip()
    if not text:
        return ""
    if not is_encrypted(text):
        return text
    token = text[len(_ENCRYPT_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def encrypt_if_needed(value: str) -> str:
    return encrypt_value(value) if value else ""
