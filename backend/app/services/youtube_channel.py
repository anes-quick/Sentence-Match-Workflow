"""
Resolve YouTube video ID to channel ID via YouTube Data API v3.
Used so the Sources sheet keys by channel (one SRC ID per channel).
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT = 10.0


def get_channel_id_from_video(video_id: str) -> Optional[str]:
    """
    Return the channel ID (e.g. UC...) for the given YouTube video ID.
    Returns None if YOUTUBE_API_KEY is not set or the request fails.
    """
    api_key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        logger.debug("YOUTUBE_API_KEY not set, cannot resolve channel_id")
        return None
    if not (video_id or "").strip():
        return None
    video_id = video_id.strip()
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            r = client.get(
                f"{YOUTUBE_API_BASE}/videos",
                params={"part": "snippet", "id": video_id, "key": api_key},
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("items") or []
            if not items:
                logger.info("YouTube API returned no items for video_id=%s", video_id)
                return None
            channel_id = (items[0].get("snippet") or {}).get("channelId") or None
            if channel_id:
                logger.debug("Resolved video_id=%s -> channel_id=%s", video_id, channel_id)
            return channel_id
    except Exception as e:
        logger.warning("YouTube API failed for video_id=%s: %s", video_id, e)
        return None
