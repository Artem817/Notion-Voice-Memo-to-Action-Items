import pytest
from app.services.notion_publisher import _normalize_date


class TestNormalizeDate:
    """Tests for the date normalization utility used before publishing to Notion."""

    def test_standard_date(self):
        assert _normalize_date("2026-09-21") == "2026-09-21"

    def test_iso_datetime(self):
        assert _normalize_date("2026-09-21T14:30:00") == "2026-09-21"

    def test_iso_datetime_with_utc(self):
        assert _normalize_date("2026-09-21T14:30:00Z") == "2026-09-21"

    def test_iso_datetime_with_offset(self):
        assert _normalize_date("2026-09-21T14:30:00+03:00") == "2026-09-21"

    def test_none_input(self):
        assert _normalize_date(None) is None

    def test_empty_string(self):
        assert _normalize_date("") is None

    def test_garbage_string(self):
        assert _normalize_date("not a date") is None

    def test_partial_iso_prefix(self):
        assert _normalize_date("2026-09-21 some extra text") == "2026-09-21"
