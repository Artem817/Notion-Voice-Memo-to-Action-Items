import pytest
from app.utils import extract_notion_database_id


class TestExtractNotionDatabaseId:
    """Tests for extracting Notion database IDs from various URL formats and raw IDs."""

    def test_full_notion_url(self):
        url = "https://www.notion.so/workspace/abcdef0123456789abcdef0123456789?v=xyz"
        assert extract_notion_database_id(url) == "abcdef0123456789abcdef0123456789"

    def test_uuid_with_dashes(self):
        raw = "abcdef01-2345-6789-abcd-ef0123456789"
        assert extract_notion_database_id(raw) == "abcdef0123456789abcdef0123456789"

    def test_raw_32_hex(self):
        raw = "abcdef0123456789abcdef0123456789"
        assert extract_notion_database_id(raw) == "abcdef0123456789abcdef0123456789"

    def test_uppercase_normalized_to_lower(self):
        raw = "ABCDEF0123456789ABCDEF0123456789"
        assert extract_notion_database_id(raw) == "abcdef0123456789abcdef0123456789"

    def test_none_input(self):
        assert extract_notion_database_id(None) is None

    def test_empty_string(self):
        assert extract_notion_database_id("") is None

    def test_invalid_string(self):
        assert extract_notion_database_id("not-a-database-id") is None

    def test_too_short_hex(self):
        assert extract_notion_database_id("abcdef01234567") is None
