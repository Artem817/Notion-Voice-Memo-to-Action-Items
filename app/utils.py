import re


def extract_notion_database_id(text: str | None) -> str | None:
    """Extract a Notion database ID from a URL or raw hex string.

    Accepts both 32-character hex IDs and UUID-formatted IDs (with dashes).
    Returns a normalized 32-character lowercase hex string, or None if no ID is found.
    """
    if not text:
        return None
    match = re.search(
        r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})",
        text,
    )
    if not match:
        return None
    raw_id = match.group(1)
    return raw_id.replace("-", "").lower()
