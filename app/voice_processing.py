from pathlib import Path
from pydantic import BaseModel, ConfigDict, field_validator
from whisper import Whisper


# nlp_en = spacy.load("en_core_web_sm")

# morph = pymorphy3.MorphAnalyzer()

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


    
    
    # @field_validator("audio_transcription")
    # def validate_audio_transcription(cls, value):
    #     if not value:
    #         raise ValueError("Audio transcription cannot be empty")
    #     return value

    # @model_validator(mode='after')
    # def validate_transcription_by_language(self):
    #     text = self.audio_transcription.strip()
        
    #     if self.language == "en":
    #         doc = nlp_en(text)
    #         valid_tokens = sum(1 for token in doc if token.is_alpha and not token.is_stop)
    #         if valid_tokens < 1:
    #             raise ValueError("English transcription must contain valid words")
                
    #     elif self.language == "uk":
    #         words = [w.strip(".,!?\"()-") for w in text.split()]
    #         valid_words = 0
            
    #         for word in words:
    #             if not word.isalpha():
    #                 continue
                    
    #             parsed_variants = morph.parse(word)
    #             if any(p.is_known for p in parsed_variants):
    #                 valid_words += 1
            
    #         if valid_words < 1:
    #             raise ValueError("Ukrainian transcription must contain recognized words")
        
    #     return self
