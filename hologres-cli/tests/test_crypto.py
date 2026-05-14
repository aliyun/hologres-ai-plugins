"""Tests for hologres_cli.crypto module."""

import os
import stat

import pytest

from hologres_cli.crypto import ENC_PREFIX, decrypt, encrypt, is_encrypted, _get_or_create_key, _key_file


class TestEncryptDecrypt:
    """Test encrypt/decrypt roundtrip and edge cases."""

    def test_encrypt_decrypt_roundtrip(self, tmp_path, monkeypatch):
        """Encrypt then decrypt returns original value."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        plaintext = "my-secret-password-123!@#"
        encrypted = encrypt(plaintext)
        assert encrypted.startswith(ENC_PREFIX)
        assert decrypt(encrypted) == plaintext

    def test_encrypt_decrypt_unicode(self, tmp_path, monkeypatch):
        """Unicode passwords encrypt/decrypt correctly."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        plaintext = "密码测试123!@#中文"
        encrypted = encrypt(plaintext)
        assert decrypt(encrypted) == plaintext

    def test_decrypt_plaintext_passthrough(self, tmp_path, monkeypatch):
        """Non-encrypted values are returned as-is (backward compat)."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        plaintext = "plain-password-no-prefix"
        assert decrypt(plaintext) == plaintext

    def test_decrypt_empty_string(self, tmp_path, monkeypatch):
        """Empty string returns empty string."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        assert decrypt("") == ""

    def test_encrypt_empty_string(self, tmp_path, monkeypatch):
        """Empty string is not encrypted."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        assert encrypt("") == ""

    def test_is_encrypted(self, tmp_path, monkeypatch):
        """is_encrypted correctly identifies encrypted values."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        encrypted = encrypt("test")
        assert is_encrypted(encrypted) is True
        assert is_encrypted("plaintext") is False
        assert is_encrypted("") is False

    def test_key_file_permissions(self, tmp_path, monkeypatch):
        """Key file is created with 0600 permissions."""
        key_path = tmp_path / ".cipher_key"
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: key_path)
        _get_or_create_key()
        assert key_path.exists()
        mode = stat.S_IMODE(os.stat(key_path).st_mode)
        assert mode == 0o600

    def test_key_persistence(self, tmp_path, monkeypatch):
        """Same key is reused across calls."""
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: tmp_path / ".cipher_key")
        key1 = _get_or_create_key()
        key2 = _get_or_create_key()
        assert key1 == key2

    def test_decrypt_with_wrong_key_returns_empty(self, tmp_path, monkeypatch):
        """Decryption with wrong key returns empty string (graceful failure)."""
        key_path = tmp_path / ".cipher_key"
        monkeypatch.setattr("hologres_cli.crypto._key_file", lambda: key_path)

        # Encrypt with one key
        encrypted = encrypt("secret")

        # Replace key file with a different key
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key()
        key_path.write_bytes(new_key)

        # Decrypt should return empty (not crash)
        assert decrypt(encrypted) == ""
