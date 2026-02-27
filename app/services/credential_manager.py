from sqlalchemy.orm import Session

from app.db import models
from app.services.notion_vault import NotionVault


class NotionKeyPipline:
    def __init__(self, raw_string: str, master_key: str):
        self._raw = raw_string
        try:
            self._vault = NotionVault(master_key)
        except Exception as exc:
            raise RuntimeError("MASTER_KEY is invalid") from exc
        self.clean_data = None
        self.encrypted_blob = None

    def step_1_sanitize(self):
        if not self._raw:
            raise ValueError("Input string is empty")
        self.clean_data = self._raw.strip()
        if not self.clean_data:
            raise ValueError("Input string is empty after sanitization")
        return self

    def step_2_validation(self):
        if not self.clean_data.startswith("secret_"):
            raise ValueError("Notion API key must start with 'secret_'")
        if len(self.clean_data) < 20:
            raise ValueError("Notion API key is too short to be valid")
        return self

    def step_3_encrypt(self):
        self.encrypted_blob = self._vault.encrypt_key(self.clean_data)
        self.clean_data = "CLEARED"
        return self

    def save_to_db(
        self,
        db: Session,
        user_id: int,
        workspace_name: str,
        database_id: str | None = None,
    ):
        if self.encrypted_blob is None:
            raise RuntimeError("Key must be encrypted before saving")
        credential = db.query(models.NotionCredential).filter_by(user_id=user_id).first()
        if credential:
            credential.workspace_name = workspace_name
            credential.encrypted_key = self.encrypted_blob
            if database_id is not None:
                credential.database_id = database_id
        else:
            credential = models.NotionCredential(
                user_id=user_id,
                workspace_name=workspace_name,
                encrypted_key=self.encrypted_blob,
                database_id=database_id,
            )
            db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential
