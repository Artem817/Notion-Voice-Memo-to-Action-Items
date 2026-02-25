from pydantic import BaseModel
from typing import List
from app.voice_processing import VoiceProcessingRequest

class WhisperSegment(BaseModel):
    id: int
    seek: int
    start: float
    end: float
    text: str
    tokens: List[int]
    temperature: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float

class WhisperResult(BaseModel):
    text: str
    segments: List[WhisperSegment]
    language: str

def transcribe_audio(voice_request_obg: VoiceProcessingRequest) -> WhisperResult:
    """
    Transcribes the audio file at the given path and returns the transcription text.
    
    Args:
        file_path (Path): The path to the audio file to be transcribed. 
        
    Returns:
        str: The transcription text.
    """
    if voice_request_obg.model is None:
        raise ValueError("Whisper model is not loaded.")

    result = voice_request_obg.model.transcribe(str(voice_request_obg.file_path))
    return WhisperResult(
        text=result["text"],
        segments=[WhisperSegment(**segment) for segment in result.get("segments", [])],
        language=result.get("language", "")
    )
