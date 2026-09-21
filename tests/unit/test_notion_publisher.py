import pytest
from app.services.notion_publisher import NotionPublisher

class TestNotionPublisher:
    @pytest.fixture
    def publisher(self):
        # Mock session_factory and master_key, we won't use them for payload building
        return NotionPublisher(session_factory=lambda: None, master_key="mock_key")

    def test_build_page_payload(self, publisher):
        payload = publisher._build_page_payload(
            database_id="test_db_id",
            title="Test Title",
            tasks=["Task 1", "Task 2"],
            transcript="Test transcript",
            date_value="2026-09-21",
            priority="High"
        )

        assert payload["parent"]["database_id"] == "test_db_id"
        assert payload["properties"]["Name"]["title"][0]["text"]["content"] == "Test Title"
        assert payload["properties"]["Priority"]["select"]["name"] == "High"
        assert payload["properties"]["Date"]["date"]["start"] == "2026-09-21"

        # Check blocks
        blocks = payload["children"]
        # Summary Heading, Summary Text, Action Items Heading, Task 1, Task 2, Divider, Transcript
        assert len(blocks) == 7
        assert blocks[0]["type"] == "heading_2"
        assert blocks[1]["type"] == "paragraph"
        assert blocks[2]["type"] == "heading_2"
        assert blocks[3]["type"] == "to_do"
        assert blocks[3]["to_do"]["rich_text"][0]["text"]["content"] == "Task 1"
        assert blocks[4]["to_do"]["rich_text"][0]["text"]["content"] == "Task 2"
        assert blocks[5]["type"] == "divider"
        assert blocks[6]["type"] == "paragraph"
