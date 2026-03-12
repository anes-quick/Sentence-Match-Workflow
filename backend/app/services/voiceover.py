"""
Voice-over: ElevenLabs only.
TTS text is cleaned of [speak fast] and similar bracket instructions before sending to the API.
"""
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = "https://api.elevenlabs.io"
ELEVENLABS_VOICE_ID = "z71EjgDq5DjMmSU6Azn9"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Per-voice IDs for ElevenLabs (frontend sends voice_key; we map to the right id).
VOICE_IDS = {
    "fast_mf": {"elevenlabs": "z71EjgDq5DjMmSU6Azn9"},
    "helmut": {"elevenlabs": "JiW03c2Gt43XNUQAumRP"},
    "lars": {"elevenlabs": "raYPS0b2ZPlIzZWkcD0G"},
}


def strip_tts_instructions(text: str) -> str:
    """
    Remove [speak fast] and similar bracket-only lines so the TTS API doesn't speak them.
    Display/copy text is unchanged; only the payload sent to ai33/ElevenLabs is cleaned.
    """
    if not text or not text.strip():
        return text
    # Remove [speak fast] (case insensitive) and optional surrounding space
    out = re.sub(r"\[speak\s+fast\]\s*", "", text, flags=re.IGNORECASE)
    # Remove lines that are only a single [bracket] tag (TTS instructions)
    lines = out.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\[[^\]]+\]$", stripped):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _generate_voiceover_elevenlabs(tts_text: str, voice_id_override: str = None) -> bytes:
    """ElevenLabs direct TTS — synchronous, returns MP3 bytes. Used as fallback when ai33 is slow/fails."""
    api_key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is not set (required for fallback)")
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {"text": tts_text, "model_id": ELEVENLABS_MODEL}
    requested_voice_id = (voice_id_override or "").strip() or None
    default_voice_id = (os.environ.get("ELEVENLABS_VOICE_ID") or ELEVENLABS_VOICE_ID).strip()

    def _post(voice_id: str) -> httpx.Response:
        url = f"{ELEVENLABS_BASE}/v1/text-to-speech/{voice_id}"
        return client.post(url, json=body, headers=headers)

    with httpx.Client(timeout=60.0) as client:
        # First try the requested voice_id (if provided), otherwise default.
        primary_voice_id = requested_voice_id or default_voice_id
        r = _post(primary_voice_id)
        try:
            r.raise_for_status()
            return r.content
        except httpx.HTTPStatusError as e:
            # Common failure mode: frontend sends an ai33-only voice id (e.g. "Lars" id)
            # and we fall back to ElevenLabs; ElevenLabs then responds 404/422.
            status = e.response.status_code
            if requested_voice_id and primary_voice_id != default_voice_id and status in (404, 422, 400):
                logger.warning(
                    "ElevenLabs rejected voice_id=%s with %s; retrying with default ELEVENLABS_VOICE_ID=%s",
                    primary_voice_id,
                    status,
                    default_voice_id,
                )
                r2 = _post(default_voice_id)
                r2.raise_for_status()
                return r2.content
            raise


def _voice_id_for_provider(voice_key: str) -> str:
    """Resolve ElevenLabs voice id from voice_key, or empty string if unknown key."""
    key = (voice_key or "").strip().lower() if voice_key else ""
    if key in VOICE_IDS:
        return VOICE_IDS[key].get("elevenlabs") or ""
    return ""


def generate_voiceover(tts_text: str, voice_id: str = None, voice_key: str = None) -> bytes:
    """
    Generate voice-over via ElevenLabs only.
    Strips [speak fast] and bracket-only lines before sending to the TTS API.
    Prefer voice_key (fast_mf, helmut, lars) for per-voice ids; otherwise voice_id/env default is used.
    """
    clean_text = strip_tts_instructions(tts_text)
    vid = (voice_id or "").strip() or None
    vkey = (voice_key or "").strip() or None
    el_id = _voice_id_for_provider(vkey) if vkey else None
    if not el_id:
        el_id = vid
    return _generate_voiceover_elevenlabs(clean_text, voice_id_override=el_id or None)
