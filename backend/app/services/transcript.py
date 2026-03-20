import os

import httpx

FETCHTRANSCRIPT_BASE = "https://api.fetchtranscript.com/v1"
TRANSCRIPTAPI_BASE = "https://transcriptapi.com/api/v2"
DEFAULT_TIMEOUT = 15.0

PROVIDER_FETCHTRANSCRIPT = "fetchtranscript"
PROVIDER_TRANSCRIPTAPI = "transcriptapi"
_VALID_PROVIDERS = {PROVIDER_FETCHTRANSCRIPT, PROVIDER_TRANSCRIPTAPI}


def _normalize_provider(value: str, default: str) -> str:
    provider = (value or "").strip().lower() or default
    if provider not in _VALID_PROVIDERS:
        return default
    return provider


def _provider_order() -> list[str]:
    """
    Build provider priority list from env:
    - TRANSCRIPT_PROVIDER_PRIMARY (default: transcriptapi)
    - TRANSCRIPT_PROVIDER_FALLBACK (default: fetchtranscript)
    """
    primary = _normalize_provider(
        os.environ.get("TRANSCRIPT_PROVIDER_PRIMARY", ""),
        PROVIDER_TRANSCRIPTAPI,
    )
    fallback = _normalize_provider(
        os.environ.get("TRANSCRIPT_PROVIDER_FALLBACK", ""),
        PROVIDER_FETCHTRANSCRIPT,
    )
    order = [primary]
    if fallback != primary:
        order.append(fallback)
    return order


async def _fetchtranscript_transcript(video_id: str) -> dict:
    api_key = os.environ.get("FETCHTRANSCRIPT_API_KEY")
    if not api_key:
        raise ValueError("FETCHTRANSCRIPT_API_KEY is not set")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        r = await client.get(
            f"{FETCHTRANSCRIPT_BASE}/transcripts/{video_id}",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return r.json()


async def _fetchtranscript_metadata(video_id: str) -> dict:
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


async def _transcriptapi_transcript(video_id: str) -> dict:
    api_key = os.environ.get("TRANSCRIPTAPI_API_KEY")
    if not api_key:
        raise ValueError("TRANSCRIPTAPI_API_KEY is not set")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        r = await client.get(
            f"{TRANSCRIPTAPI_BASE}/youtube/transcript",
            params={
                "video_url": video_id,
                "format": "json",
                "include_timestamp": "false",
                "send_metadata": "true",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        payload = r.json()

    # Normalize to the shape expected by process.py
    segments = payload.get("transcript") or []
    metadata = payload.get("metadata") or {}
    return {
        "segments": segments,
        "metadata": {
            "title": metadata.get("title") or "",
            "author": metadata.get("author_name") or "",
            "channelTitle": metadata.get("author_name") or "",
        },
    }


async def _transcriptapi_metadata(video_id: str) -> dict:
    api_key = os.environ.get("TRANSCRIPTAPI_API_KEY")
    if not api_key:
        raise ValueError("TRANSCRIPTAPI_API_KEY is not set")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        r = await client.get(
            f"{TRANSCRIPTAPI_BASE}/youtube/transcript",
            params={
                "video_url": video_id,
                "format": "json",
                "include_timestamp": "false",
                "send_metadata": "true",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        payload = r.json()
    meta = payload.get("metadata") or {}
    return {
        "title": meta.get("title") or "",
        "author": meta.get("author_name") or "",
        "channelTitle": meta.get("author_name") or "",
        # TranscriptAPI does not return full description.
        "description": "",
    }


async def get_transcript(video_id: str) -> dict:
    """Fetch transcript with configurable primary/fallback provider order."""
    errors: list[str] = []
    for provider in _provider_order():
        try:
            if provider == PROVIDER_TRANSCRIPTAPI:
                return await _transcriptapi_transcript(video_id)
            return await _fetchtranscript_transcript(video_id)
        except Exception as e:
            errors.append(f"{provider}: {e}")
    raise RuntimeError("All transcript providers failed: " + " | ".join(errors))


async def get_video_metadata(video_id: str) -> dict:
    """Fetch video metadata with configurable primary/fallback provider order."""
    errors: list[str] = []
    for provider in _provider_order():
        try:
            if provider == PROVIDER_TRANSCRIPTAPI:
                return await _transcriptapi_metadata(video_id)
            return await _fetchtranscript_metadata(video_id)
        except Exception as e:
            errors.append(f"{provider}: {e}")
    raise RuntimeError("All metadata providers failed: " + " | ".join(errors))
