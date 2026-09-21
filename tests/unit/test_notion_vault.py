import pytest
from cryptography.fernet import Fernet

from app.services.notion_vault import NotionVault


class TestNotionVault:
    """Tests for the Fernet-based encryption/decryption of Notion API keys."""

    @pytest.fixture
    def vault(self):
        key = Fernet.generate_key().decode()
        return NotionVault(key)

    def test_encrypt_decrypt_roundtrip(self, vault):
        original = "secret_abc123xyz"
        encrypted = vault.encrypt_key(original)
        decrypted = vault.decrypt_key(encrypted)
        assert decrypted == original

    def test_encrypted_value_differs_from_plaintext(self, vault):
        original = "secret_abc123xyz"
        encrypted = vault.encrypt_key(original)
        assert encrypted != original.encode()

    def test_decrypt_with_wrong_key_fails(self, vault):
        encrypted = vault.encrypt_key("secret_abc123xyz")
        other_vault = NotionVault(Fernet.generate_key().decode())
        with pytest.raises(Exception):
            other_vault.decrypt_key(encrypted)

    def test_whitespace_stripped(self, vault):
        original = "  secret_abc123xyz  "
        encrypted = vault.encrypt_key(original)
        decrypted = vault.decrypt_key(encrypted)
        assert decrypted == "secret_abc123xyz"
