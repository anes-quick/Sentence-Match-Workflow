import os
import httpx

FETCHTRANSCRIPT_BASE = "https://api.fetchtranscript.com/v1"
DEFAULT_TIMEOUT = 15.0


async def get_transcript(video_id: str) -> dict:
    """Fetch transcript (JSON with segments) for a YouTube video."""
    api_key = os.environ.get("FETCHTRANSCRIPT_API_KEY")
    if not api_key:
        raise ValueError("FETCHTRANSCRIPT_API_KEY is not set")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # Don't force lang: get the video's transcript (any language); Claude will translate
        r = await client.get(
            f"{FETCHTRANSCRIPT_BASE}/transcripts/{video_id}",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return r.json()


async def get_video_metadata(video_id: str) -> dict:
    """Fetch video metadata (title, description, etc.) for credits."""
    api_key = os.environ.get("FETCHTRANSCRIPT_API_KEY")
    if not api_key:
        raise ValueError("FETCHTRANSCRIPT_API_KEY is not set")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        r = await client.get(
            f"{FETCHTRANSCRIPT_BASE}/videos/{video_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return r.json()
