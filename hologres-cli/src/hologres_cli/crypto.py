"""Credential encryption for Hologres CLI config.

Uses Fernet symmetric encryption (from the `cryptography` package).
The encryption key is stored at ~/.hologres/.cipher_key with permissions 0600.
Encrypted values are prefixed with "ENC:" for identification.
Plaintext values (without prefix) are returned as-is for backward compatibility.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ENC_PREFIX = "ENC:"


def _key_file() -> Path:
    """Return the path to the cipher key file. Evaluated at runtime."""
    return Path.home() / ".hologres" / ".cipher_key"


def _get_or_create_key() -> bytes:
    """Load existing key or generate a new one.

    The key file is created with permissions 0600 (owner read/write only).
    """
    key_path = _key_file()

    if key_path.exists():
        return key_path.read_bytes().strip()

    # Generate a new Fernet key
    key = Fernet.generate_key()

    # Ensure directory exists
    key_path.parent.mkdir(parents=True, exist_ok=True)

    # Write key with restricted permissions
    # Create file with 0600 permissions
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)

    return key


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string.

    Returns a string prefixed with "ENC:" followed by the Fernet token.
    Empty strings are returned as-is (no encryption needed).
    """
    if not plaintext:
        return plaintext

    key = _get_or_create_key()
    f = Fernet(key)
    token = f.encrypt(plaintext.encode("utf-8"))
    return ENC_PREFIX + token.decode("ascii")


def decrypt(value: str) -> str:
    """Decrypt a value if it's encrypted (ENC: prefix), otherwise return as-is.

    This provides backward compatibility with plaintext config values.
    """
    if not value or not isinstance(value, str):
        return value

    if not value.startswith(ENC_PREFIX):
        # Plaintext value — return as-is (backward compat)
        return value

    token = value[len(ENC_PREFIX):].encode("ascii")
    key = _get_or_create_key()
    f = Fernet(key)
    try:
        return f.decrypt(token).decode("utf-8")
    except InvalidToken:
        # If decryption fails (e.g., key was rotated), return empty
        # This prevents crashes; user will need to re-enter credentials
        return ""


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted (has the ENC: prefix)."""
    return isinstance(value, str) and value.startswith(ENC_PREFIX)
