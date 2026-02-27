from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import UUID4, BaseModel, Field

class AdditionalInfo(BaseModel):
    priority: str | None = Field(default=None, description="Low, Medium, or High")
    category: str | None = Field(default=None, description="Grammar, Vocabulary, or Speaking")

class GemJsonResponseSchema(BaseModel):
    id: UUID4 = Field(description="Generate a unique UUIDv4 for this entry")
    task_date_from_user: datetime = Field(
        ..., 
        description="Extract the date from user's text and format as ISO 8601"
    )
    tasks: List[str] = Field(
        ..., 
        min_items=1,
        description="A list of specific task strings"
    )
    additional_info: AdditionalInfo | None = Field(
        default=None,
        description="Optional extra context like priority or category",
    )
    additional_recommendation: str | None = Field(
        default=None,
        description="Optional recommendations based on the tasks",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="The current timestamp"
    )   
    
    def __str__(self):
        parts: list[str] = [
            f"ID: {self.id}",
            f"Task Date: {self.task_date_from_user.isoformat()}",
            f"Tasks: {self.tasks}",
        ]
        if self.additional_info and (self.additional_info.priority or self.additional_info.category):
            parts.append(f"Additional Info: {self.additional_info}")
        if self.additional_recommendation:
            parts.append(f"Additional Recommendation: {self.additional_recommendation}")
        parts.append(f"Created At: {self.created_at.isoformat()}")
        return "\n".join(parts)
    
    
async def process_gem_response(gem_response: Dict[str, Any]) -> GemJsonResponseSchema:
    """
    Process the raw response from Gemini and convert it into a structured format
    that matches the GemJsonResponseSchema.
    
    Args:
        gem_response (Dict[str, Any]): The raw response from Gemini, expected to contain a 'text' field with the user's input.
        user_id (str): The ID of the user who made the request.

    Returns:
        GemJsonResponseSchema: The processed response conforming to the schema.
    """
    text = gem_response.get("text", "")
    tasks = text.split("\n") if text else []

    return GemJsonResponseSchema(
        id=str(uuid4()),
        task_date_from_user=datetime.now(),
        tasks=tasks,
        additional_info=gem_response.get("additional_info", {}),
        additional_recommendation=gem_response.get("additional_recommendation"),
        created_at=datetime.now()
    )
