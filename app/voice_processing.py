from pathlib import Path
from pydantic import BaseModel, ConfigDict, field_validator
from whisper import Whisper


class VoiceProcessingRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    file_id: str
    user_id: str
    file_path: Path
    model: Whisper | None = None
    
    @field_validator("file_path")
    def validate_file_path(cls, value):
        path = Path(value)
        if not path.exists():
            raise ValueError(f"File path does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")
        return path
