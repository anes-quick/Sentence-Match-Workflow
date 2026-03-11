import re
from typing import Optional

# YouTube URL patterns: watch?v=ID, shorts/ID, embed/ID, youtu.be/ID
YOUTUBE_ID_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL. Returns None if not valid."""
    if not url or not url.strip():
        return None
    url = url.strip()
    # Allow pasting just the ID
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    match = YOUTUBE_ID_PATTERN.search(url)
    return match.group(1) if match else None
