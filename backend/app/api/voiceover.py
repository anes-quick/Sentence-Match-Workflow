import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import voiceover as voiceover_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voiceover", tags=["voiceover"])


class VoiceoverRequest(BaseModel):
    tts_text: str
    voice_id: Optional[str] = None
    voice_key: Optional[str] = None  # "fast_mf" | "helmut" | "lars" → per-platform ids used


@router.post("", response_class=Response)
def create_voiceover(body: VoiceoverRequest):
    """
    Generate voice-over from TTS text via ai33 / ElevenLabs.
    Prefer voice_key for correct id per platform; optional voice_id used if no voice_key.
    Returns MP3 audio file for download.
    """
    text = (body.tts_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="tts_text is required and cannot be empty.")
    voice_id = (body.voice_id or "").strip() or None
    voice_key = (body.voice_key or "").strip() or None
    try:
        audio_bytes = voiceover_service.generate_voiceover(text, voice_id=voice_id, voice_key=voice_key)
    except ValueError as e:
        if "AI33" in str(e):
            raise HTTPException(status_code=502, detail="Voice-over service not configured.")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Voice-over generation failed")
        raise HTTPException(status_code=502, detail=f"Voice-over failed: {str(e)}")
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "attachment; filename=voiceover.mp3"},
    )
