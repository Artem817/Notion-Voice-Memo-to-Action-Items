from pydantic import BaseModel
from app.voice_processing import VoiceProcessingRequest

class WhisperSegment(BaseModel):
    id: int
    seek: int
    start: float
    end: float
    text: str
    tokens: list[int]
    temperature: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float

class WhisperResult(BaseModel):
    text: str
    segments: list[WhisperSegment]
    language: str

def transcribe_audio(voice_request: VoiceProcessingRequest) -> WhisperResult:
    """
    Transcribes the audio file using the Whisper model attached to the request.

    Args:
        voice_request: A validated request containing the file path and loaded Whisper model.

    Returns:
        WhisperResult: The transcription text, segments, and detected language.
    """
    if voice_request.model is None:
        raise ValueError("Whisper model is not loaded.")

    result = voice_request.model.transcribe(str(voice_request.file_path))
    return WhisperResult(
        text=result["text"],
        segments=[WhisperSegment(**segment) for segment in result.get("segments", [])],
        language=result.get("language", "")
    )
