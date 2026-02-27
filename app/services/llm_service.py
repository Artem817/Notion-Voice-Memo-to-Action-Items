import os
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class AdditionalInfo(BaseModel):
    priority: Optional[str] = Field(default="Medium", description="Low, Medium, or High")
    category: Optional[str] = Field(default="General", description="Grammar, Vocabulary, Speaking, or General")

class GemJsonResponseSchema(BaseModel):
    title: str = Field(description="Short text-based note title")
    task_date_from_user: str = Field(description="YYYY-MM-DD format")
    tasks: List[str] = Field(min_items=1, description="List of tasks")
    priority: str = Field(default="Normal", description="High, Medium, Normal, or Low")
    should_ignore: bool = Field(default=False, description="True if user wants to cancel or ignore")

class ProcessedMemo(BaseModel):
    id: str
    created_at: datetime
    llm_data: GemJsonResponseSchema
class GeminiLLMService:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env!")
        
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"
        
        self.system_instruction = (
            "You are a smart assistant. Your goal is to convert voice transcriptions "
            "into structured Notion notes. "
            "IMPORTANT: Always calculate the exact date based on the 'Current Date' provided in the prompt. "
            "If the user says 'tomorrow', 'next Friday', or 'in 5 days', calculate the YYYY-MM-DD. "
            "If no date is mentioned, use the Current Date."
        )

    async def structure_transcript(self, transcript: str) -> ProcessedMemo:
        today_context = datetime.now().strftime("%Y-%m-%d (Day of week: %A)")
        
        prompt = f"Current Date: {today_context}\n\nUser Transcript: {transcript}"
        
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            response_mime_type="application/json",
            response_schema=GemJsonResponseSchema,
            temperature=0.1, 
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=config
        )

        llm_result = response.parsed

        return ProcessedMemo(
            id=str(uuid4()),
            created_at=datetime.now(),
            llm_data=llm_result
        )