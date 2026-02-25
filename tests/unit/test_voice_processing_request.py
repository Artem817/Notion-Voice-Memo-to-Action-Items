import pytest
import json
import os
from pydantic import ValidationError
from app.voice_processing import VoiceProcessingRequest

def load_fixtures():
    path = os.path.join(os.path.dirname(__file__), "fixtures/content_ex.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

fixtures = load_fixtures()

@pytest.mark.parametrize("item", fixtures["valid"])
def test_voice_request_validation_valid(tmp_path, item):
    """These cases must proceed without errors"""
    file_path = tmp_path / item["file_name"]
    file_path.write_bytes(b"dummy audio")

    request_obj = VoiceProcessingRequest(
        file_id=item["file_id"],
        user_id=item["user_id"],
        file_path=file_path,
    )
    assert request_obj.file_id == item["file_id"]
    assert request_obj.user_id == item["user_id"]
    assert request_obj.file_path == file_path

@pytest.mark.parametrize("item", fixtures["invalid"])
def test_voice_request_validation_invalid(tmp_path, item):
    """These cases must raise ValidationError"""
    file_path = tmp_path / item["file_name"]
    if item.get("is_dir"):
        file_path.mkdir()

    with pytest.raises(ValidationError):
        VoiceProcessingRequest(
            file_id=item["file_id"],
            user_id=item["user_id"],
            file_path=file_path,
        )
