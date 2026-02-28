"""Unit tests for the encryption module."""
import pytest


class TestEncryption:
    """Test field-level encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        from app.core.encryption import encrypt_field, decrypt_field
        plaintext = "my-secret-password-123!"
        encrypted = encrypt_field(plaintext)
        assert encrypted != plaintext
        assert encrypted.startswith("gAAAAA")
        decrypted = decrypt_field(encrypted)
        assert decrypted == plaintext

    def test_encrypt_empty_string(self):
        from app.core.encryption import encrypt_field, decrypt_field
        assert encrypt_field("") == ""
        assert decrypt_field("") == ""

    def test_encrypt_none(self):
        from app.core.encryption import encrypt_field, decrypt_field
        assert encrypt_field(None) is None
        assert decrypt_field(None) is None

    def test_decrypt_plaintext_passthrough(self):
        """Legacy plaintext passwords should pass through unchanged."""
        from app.core.encryption import decrypt_field
        plain = "old-plaintext-password"
        assert decrypt_field(plain) == plain

    def test_is_encrypted(self):
        from app.core.encryption import encrypt_field, is_encrypted
        encrypted = encrypt_field("test-password")
        assert is_encrypted(encrypted) is True
        assert is_encrypted("plaintext") is False
        assert is_encrypted("") is False
        assert is_encrypted(None) is False

    def test_different_plaintexts_produce_different_ciphertexts(self):
        from app.core.encryption import encrypt_field
        enc1 = encrypt_field("password1")
        enc2 = encrypt_field("password2")
        assert enc1 != enc2

    def test_same_plaintext_produces_different_ciphertexts(self):
        """Fernet uses random IV, so same input -> different output each time."""
        from app.core.encryption import encrypt_field
        enc1 = encrypt_field("same-password")
        enc2 = encrypt_field("same-password")
        assert enc1 != enc2  # Random IV ensures uniqueness

    def test_special_characters(self):
        from app.core.encryption import encrypt_field, decrypt_field
        special = "p@$$w0rd!#%^&*()_+-={}[]|\\:\";<>?,./"
        encrypted = encrypt_field(special)
        assert decrypt_field(encrypted) == special

    def test_unicode_password(self):
        from app.core.encryption import encrypt_field, decrypt_field
        unicode_pw = "p\u00e4ssw\u00f6rd\u00fc\u00df"
        encrypted = encrypt_field(unicode_pw)
        assert decrypt_field(encrypted) == unicode_pw
