import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import transcript as transcript_service

logger = logging.getLogger(__name__)
from app.services import translate as translate_service
from app.utils.credits import extract_credits
from app.utils.video import extract_video_id

router = APIRouter(prefix="/process", tags=["process"])


class ProcessRequest(BaseModel):
    video_url: str


def _build_transcript_text(transcript: dict) -> str:
    """Build plain text from FetchTranscript segments."""
    segments = transcript.get("segments") or []
    return "\n".join(
        (s.get("text") or "").strip() for s in segments if s.get("text")
    ).strip()


def _extract_source_handle(transcript: dict, metadata: dict) -> str:
    """
    Try to get the uploader/channel handle for 'Source -'.
    Priority:
    - transcript.metadata.channel / channelTitle / author / uploader
    - metadata.channel / channelTitle / author / uploader
    Normalize to '@handle' when possible.
    """
    tm = transcript.get("metadata") or {}
    cand = (
        tm.get("channel")
        or tm.get("channelTitle")
        or tm.get("author")
        or tm.get("uploader")
        or metadata.get("channel")
        or metadata.get("channelTitle")
        or metadata.get("author")
        or metadata.get("uploader")
        or ""
    )
    raw = (cand or "").strip()
    if not raw:
        return ""
    # If there's already an @handle in the string, use that.
    m = re.search(r"@[\w\.\-]+", raw)
    if m:
        return m.group(0)
    # If it's a simple one-word name, prefix @.
    if " " not in raw and len(raw) <= 40:
        return f"@{raw}"
    return raw


@router.post("", response_model=dict)
async def process_video(body: ProcessRequest) -> dict:
    """
    Process a YouTube video: fetch transcript + metadata, translate via Claude,
    extract credits. Returns translated_title, sentence_match, tts_text, credits, original_title.
    """
    video_url = (body.video_url or "").strip()
    video_id = extract_video_id(video_url)
    if not video_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid or missing video URL. Use a YouTube link or 11-character video ID.",
        )

    try:
        # Fetch transcript and video metadata in parallel
        transcript_task = asyncio.create_task(
            transcript_service.get_transcript(video_id)
        )
        metadata_task = asyncio.create_task(
            transcript_service.get_video_metadata(video_id)
        )
        transcript = await transcript_task
        metadata = await metadata_task
    except Exception as e:
        logger.exception("Transcript or metadata fetch failed")
        msg = str(e)
        if "401" in msg or "invalid_api_key" in msg or "missing_api_key" in msg:
            raise HTTPException(status_code=502, detail="Transcript service auth failed.")
        if "402" in msg or "insufficient_credits" in msg:
            raise HTTPException(status_code=502, detail="Transcript service out of credits.")
        if "404" in msg or "not found" in msg.lower():
            raise HTTPException(status_code=404, detail="Video or transcript not found.")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch transcript or metadata: {msg}",
        )

    transcript_text = _build_transcript_text(transcript)
    if not transcript_text:
        raise HTTPException(
            status_code=422,
            detail="No transcript text available for this video.",
        )

    original_title = (
        transcript.get("metadata", {}).get("title")
        or metadata.get("title")
        or "Untitled"
    )

    try:
        translated_title, sentence_match, tts_text = await asyncio.to_thread(
            translate_service.translate_transcript,
            transcript_text,
            original_title,
        )
    except ValueError as e:
        if "ANTHROPIC_API_KEY" in str(e):
            raise HTTPException(status_code=502, detail="Translation service not configured.")
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Translation failed: {str(e)}",
        )

    description = metadata.get("description") or ""
    credits = extract_credits(description)
    source = _extract_source_handle(transcript, metadata)

    return {
        "original_title": original_title,
        "translated_title": translated_title or original_title,
        "sentence_match": sentence_match or "",
        "tts_text": tts_text or "",
        "credits": credits,
        "source": source,
    }
