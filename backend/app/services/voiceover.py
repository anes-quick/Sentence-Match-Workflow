"""
Voice-over: try ai33 first (30s max). If it times out or fails, fall back to ElevenLabs.
After fallback, use ElevenLabs only for the next 3 hours so VA can work without delay.
TTS text is cleaned of [speak fast] and similar bracket instructions before sending to APIs.
"""
import logging
import os
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ai33
DEFAULT_VOICE_ID = "raYPS0b2ZPlIzZWkcD0G"
BASE_URL = "https://api.ai33.pro"
POLL_INTERVAL = 1.0
POLL_TIMEOUT = 30.0  # try ai33 for 30s max, then fall back to ElevenLabs

# After fallback, use ElevenLabs only for this many seconds (3 hours)
FALLBACK_WINDOW_SECONDS = 3 * 3600

# File to persist "use ElevenLabs until" timestamp (in backend dir)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_FALLBACK_UNTIL_FILE = _BACKEND_DIR / ".voiceover_fallback_until"

# ElevenLabs fallback (direct API, sync)
ELEVENLABS_BASE = "https://api.elevenlabs.io"
ELEVENLABS_VOICE_ID = "z71EjgDq5DjMmSU6Azn9"
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Per-voice IDs per platform (frontend sends voice_key; we use the right id for ai33 vs ElevenLabs).
# Fast MF: no dedicated ai33 voice → use Lars id for ai33.
VOICE_IDS = {
    "fast_mf": {"ai33": "raYPS0b2ZPlIzZWkcD0G", "elevenlabs": "z71EjgDq5DjMmSU6Azn9"},
    "helmut": {"ai33": "JiW03c2Gt43XNUQAumRP", "elevenlabs": "JiW03c2Gt43XNUQAumRP"},
    "lars": {"ai33": "raYPS0b2ZPlIzZWkcD0G", "elevenlabs": "raYPS0b2ZPlIzZWkcD0G"},
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


def _use_elevenlabs_only() -> bool:
    """True if we're within the 3-hour window after a previous fallback."""
    try:
        if _FALLBACK_UNTIL_FILE.exists():
            until = float(_FALLBACK_UNTIL_FILE.read_text().strip())
            if time.time() < until:
                return True
    except Exception:
        pass
    return False


def _set_fallback_window() -> None:
    """Record that we fell back; use ElevenLabs only for the next 3 hours."""
    try:
        until = time.time() + FALLBACK_WINDOW_SECONDS
        _FALLBACK_UNTIL_FILE.write_text(str(until))
        logger.info("Voice-over: using ElevenLabs only until %s (3h window)", time.ctime(until))
    except Exception as e:
        logger.warning("Could not write fallback window file: %s", e)


def _in_managed_env() -> bool:
    """
    Heuristic: True when running in a hosted environment like Railway.
    We prefer a simpler, more robust voice-over path there (ElevenLabs only).
    """
    return bool(
        os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("RAILWAY_PROJECT_ID")
        or os.environ.get("RAILWAY_SERVICE_NAME")
    )


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


def _voice_id_for_provider(voice_key: str, provider: str) -> str:
    """Resolve voice id for a given provider from voice_key, or None if unknown key."""
    key = (voice_key or "").strip().lower() if voice_key else ""
    if key in VOICE_IDS:
        return VOICE_IDS[key].get(provider) or ""
    return ""


def generate_voiceover(tts_text: str, voice_id: str = None, voice_key: str = None) -> bytes:
    """
    If we're in the 3h window after a previous fallback, use ElevenLabs only.
    Otherwise try ai33 (30s max); on timeout or failure, switch to ElevenLabs and set 3h window.
    Strips [speak fast] and bracket-only lines before sending to TTS APIs.
    Prefer voice_key (fast_mf, helmut, lars) for per-platform ids; otherwise voice_id is used for both.
    """
    clean_text = strip_tts_instructions(tts_text)
    vid = (voice_id or "").strip() or None
    vkey = (voice_key or "").strip() or None
    ai33_id = _voice_id_for_provider(vkey, "ai33") if vkey else None
    el_id = _voice_id_for_provider(vkey, "elevenlabs") if vkey else None
    if not ai33_id:
        ai33_id = vid
    if not el_id:
        el_id = vid

    # In managed environments (Railway) or when explicitly configured, prefer a
    # simpler and more robust path: ElevenLabs only.
    force_elevenlabs_only = (
        os.environ.get("VOICEOVER_ELEVENLABS_ONLY") == "1" or _in_managed_env()
    )

    if force_elevenlabs_only or _use_elevenlabs_only():
        logger.info("Voice-over: using ElevenLabs-only mode (managed env or 3h fallback window).")
        return _generate_voiceover_elevenlabs(clean_text, voice_id_override=el_id or None)

    try:
        return _generate_voiceover_ai33(clean_text, voice_id_override=ai33_id or None)
    except (TimeoutError, Exception) as e:
        logger.warning("ai33 voice-over failed or timed out: %s. Switching to ElevenLabs for next 3h.", e)
        _set_fallback_window()
        return _generate_voiceover_elevenlabs(clean_text, voice_id_override=el_id or None)


def _generate_voiceover_ai33(tts_text: str, voice_id_override: str = None) -> bytes:
    """Create speech via ai33: POST → task_id, poll GET task until done, fetch audio_url."""
    api_key = (os.environ.get("AI33_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("AI33_API_KEY is not set")
    voice_id = (voice_id_override or os.environ.get("AI33_VOICE_ID") or DEFAULT_VOICE_ID).strip()
    model = (os.environ.get("AI33_MODEL") or "eleven_multilingual_v2").strip()  # v2 = faster; eleven_v3 = more expressive but slower
    base_url = (os.environ.get("AI33_BASE_URL") or BASE_URL).strip().rstrip("/")

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    create_url = f"{base_url}/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    body = {
        "text": tts_text,
        "model_id": model,
        "with_transcript": False,
    }

    with httpx.Client(timeout=30.0) as client:
        r = client.post(create_url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
        if not data.get("success") or not data.get("task_id"):
            raise RuntimeError(data.get("message") or "ai33 did not return task_id")
        task_id = data["task_id"]
    logger.info("ai33 create_speech ok, task_id=%s", task_id)

    # Poll "Common / GET Task" (docs). Try paths that might match that name.
    headers_get = {"xi-api-key": api_key, "Content-Type": "application/json"}
    deadline = time.monotonic() + POLL_TIMEOUT
    last_task = None
    task_url = None
    candidates = [
        f"/v1/common/task/{task_id}",
        f"/common/task/{task_id}",
        f"/v1/task/{task_id}",
        f"/v1/tasks/{task_id}",
        f"/v1/tasks/status/{task_id}",
    ]
    with httpx.Client(timeout=15.0) as client:
        for path in candidates:
            url = base_url + path
            try:
                tr = client.get(url, headers=headers_get)
                if tr.status_code == 404:
                    continue
                tr.raise_for_status()
                first = tr.json()
                # Response must look like a task (has status or id)
                if isinstance(first, dict) and ("status" in first or "id" in first or "metadata" in first):
                    task_url = url
                    logger.info("ai33 GET task url=%s first_response_keys=%s", url, list(first.keys()))
                    break
                # Maybe wrapped in list
                if isinstance(first, list) and len(first) > 0 and isinstance(first[0], dict):
                    task_url = url
                    logger.info("ai33 GET task url=%s (list response)", url)
                    break
            except Exception as e:
                logger.debug("ai33 GET task path %s: %s", path, e)
                continue
        if not task_url:
            raise RuntimeError("ai33 GET task endpoint not found (tried: " + ", ".join(candidates) + ")")

        poll_count = 0
        while time.monotonic() < deadline:
            tr = client.get(task_url, headers=headers_get)
            tr.raise_for_status()
            raw = tr.json()
            last_task = raw
            poll_count += 1
            # Unwrap: might be { "data": {...} } or [ {...} ] or { "status": "done", ... }
            task = raw
            if isinstance(task, list) and len(task) > 0:
                for item in task:
                    if isinstance(item, dict) and (item.get("id") == task_id or "status" in item):
                        task = item
                        break
                else:
                    task = task[0] if isinstance(task[0], dict) else {}
            if isinstance(task, dict) and "data" in task and isinstance(task["data"], dict):
                task = task["data"]
            if not isinstance(task, dict):
                time.sleep(POLL_INTERVAL)
                continue
            status = (task.get("status") or task.get("state") or "").lower()
            # Treat done/completed/success as finished
            if status in ("done", "completed", "success", "succeeded"):
                meta = task.get("metadata") or task.get("result") or {}
                audio_url = meta.get("audio_url") or meta.get("output_uri") or task.get("audio_url")
                if not audio_url:
                    logger.warning("ai33 task done but no audio_url. task=%s", task)
                    raise RuntimeError("ai33 task done but no audio_url in response")
                ar = client.get(audio_url)
                ar.raise_for_status()
                logger.info("ai33 voice-over done after %d polls", poll_count)
                return ar.content
            if status in ("failed", "error", "cancelled") or task.get("error_message"):
                raise RuntimeError(task.get("error_message") or f"ai33 task status: {status}")
            if poll_count <= 2 or poll_count % 10 == 0:
                logger.info("ai33 poll #%d status=%s", poll_count, status or task)
            time.sleep(POLL_INTERVAL)

    logger.warning("ai33 voice-over timeout after %d polls. last_task=%s", poll_count, last_task)
    raise TimeoutError("ai33 voice-over task did not complete in time")
