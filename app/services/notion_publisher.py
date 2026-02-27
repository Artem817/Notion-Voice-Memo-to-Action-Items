from __future__ import annotations

import re
from typing import Callable, Sequence
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.db.models import NotionCredential
from app.services.notion_vault import NotionVault

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


class NotionPublishError(Exception):
    pass


class NotionCredentialsMissing(NotionPublishError):
    pass


class NotionApiError(NotionPublishError):
    pass


def _normalize_date(date_value: str | None) -> str | None:
    if not date_value:
        return None
    
    # Try parsing strictly as YYYY-MM-DD first
    try:
        dt = datetime.strptime(date_value, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
        
    # If that fails, try parsing with date util or handling ISO format manually if needed.
    # Given the prompt asks for stricter control, we can try to cut off time part if present
    # assuming standard ISO format YYYY-MM-DDTHH:MM:SS
    if "T" in date_value:
        try:
            dt = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
            
    # Fallback to regex if parsing fails but it looks like a date
    if re.match(r"^\d{4}-\d{2}-\d{2}", date_value):
         return date_value[:10]
         
    return None


class NotionPublisher:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        master_key: str,
        notion_version: str = NOTION_VERSION,
    ) -> None:
        self._session_factory = session_factory
        self._vault = NotionVault(master_key)
        self._notion_version = notion_version

    def _load_credentials(self, user_id: int) -> tuple[str, str]:
        with self._session_factory() as session:
            cred = session.query(NotionCredential).filter_by(user_id=user_id).first()
            if not cred or not cred.database_id:
                raise NotionCredentialsMissing("Notion credentials are missing")
            try:
                token = self._vault.decrypt_key(cred.encrypted_key)
            except Exception as exc:  # pragma: no cover - encryption failure
                raise NotionPublishError("Failed to decrypt Notion key") from exc
            return token, cred.database_id

    def _build_blocks(
        self,
        title: str,
        tasks: Sequence[str],
        transcript: str | None = None,
    ) -> list[dict]:
        blocks: list[dict] = []

        if title:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Summary:"}}]}
            })
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": title}}]}
            })

        if tasks:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Action Items:"}}]}
            })
            for task in tasks:
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"text": {"content": task.strip()}}],
                        "checked": False 
                    }
                })

        if transcript:
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        # ВИПРАВЛЕНО: annotations тепер на одному рівні з text
                        {
                            "type": "text", 
                            "text": {"content": "Original Transcript: "}, 
                            "annotations": {"italic": True}
                        },
                        {"type": "text", "text": {"content": transcript}}
                    ]
                }
            })
        return blocks

    def _build_page_payload(
        self,
        database_id: str,
        title: str,
        tasks: Sequence[str],
        transcript: str | None = None,
        date_value: str | None = None,
        priority: str = "Normal"
    ) -> dict:
        properties: dict = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Priority": {"select": {"name": priority}} # Додано пріоритет
        }
        normalized_date = _normalize_date(date_value)
        if normalized_date:
            properties["Date"] = {"date": {"start": normalized_date}}

        return {
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": self._build_blocks(title, tasks, transcript),
        }

    async def _ensure_properties_exist(self, token: str, database_id: str):
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self._notion_version,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            db_url = f"https://api.notion.com/v1/databases/{database_id}"
            response = await client.get(db_url, headers=headers)
            if response.is_error:
                raise NotionApiError(f"Failed metadata: {response.text}")
            
            existing = response.json().get("properties", {})
            to_add = {}
            
            # Перевірка Priority (Select)
            if "Priority" not in existing:
                to_add["Priority"] = {
                    "select": {
                        "options": [
                            {"name": "High", "color": "red"},
                            {"name": "Medium", "color": "yellow"},
                            {"name": "Normal", "color": "gray"},
                            {"name": "Low", "color": "blue"}
                        ]
                    }
                }
            
            if "Date" not in existing:
                to_add["Date"] = {"date": {}}
            if not any(p.get("type") == "title" for p in existing.values()):
                to_add["Name"] = {"title": {}}

            if to_add:
                await client.patch(db_url, json={"properties": to_add}, headers=headers)

    async def publish_from_user_id(
        self,
        user_id: int,
        title: str,
        tasks: Sequence[str],
        transcript: str | None = None,
        date_value: str | None = None,
        priority: str = "Normal" # Приймаємо пріоритет від LLM
    ) -> dict:
        token, database_id = self._load_credentials(user_id)
        await self._ensure_properties_exist(token, database_id)
        
        payload = self._build_page_payload(
            database_id=database_id,
            title=title,
            tasks=tasks,
            transcript=transcript,
            date_value=date_value,
            priority=priority
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self._notion_version,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(NOTION_API_URL, json=payload, headers=headers)

        if response.is_error:
            raise NotionApiError(f"Notion API error {response.status_code}: {response.text}")

        return response.json()