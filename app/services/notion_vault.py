from cryptography.fernet import Fernet


class NotionVault:
    def __init__(self, master_key: str):
        self.fernet = Fernet(master_key)

    def encrypt_key(self, raw_notion_key: str) -> bytes:
        return self.fernet.encrypt(raw_notion_key.strip().encode())

    def decrypt_key(self, encrypted_blob: bytes) -> str:
        return self.fernet.decrypt(encrypted_blob).decode()
