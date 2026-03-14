import logging
import base64
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.services import trello as trello_service
from app.services import sources_sheet as sources_sheet_service
from app.services import youtube_channel as youtube_channel_service
from app.utils.video import extract_video_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trello", tags=["trello"])


class TrelloCreateRequest(BaseModel):
    video_url: HttpUrl
    translated_title: str
    sentence_match: str
    credits: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None  # e.g. SRC0001; shown as [ SRC0001 ] below credits
    channel: Optional[str] = None
    video_number: Optional[int] = None
    force_new_folder: bool = False
    dry_run: bool = False
    voiceover_mp3_base64: Optional[str] = None  # base64 payload without data: prefix
    voiceover_filename: Optional[str] = None


class TrelloCreateResponse(BaseModel):
    card_url: str
    folder_existed: bool = False
    voiceover_uploaded: bool = False
    voiceover_upload_error: Optional[str] = None


@router.get("/test-sheet-write")
def test_sheet_write() -> dict:
    """
    Write one test row (TEST_WRITE | ok_<timestamp>_<random>) to the Sources sheet.
    Use this to verify the app can write to the sheet. You can delete the test row after.
    """
    result: dict = {"ok": False, "message": None, "error": None}
    if not sources_sheet_service.is_configured():
        result["error"] = "SOURCES_SHEET_ID is not set. Set it in Railway Variables and redeploy."
        return result
    try:
        result["message"] = sources_sheet_service.test_write_to_sheet()
        result["ok"] = True
    except sources_sheet_service.SourcesSheetError as e:
        result["error"] = str(e)
    return result


@router.get("/sources-status")
def sources_status() -> dict:
    """
    Check if the app sees the Sources sheet config (no card created).
    Use this to verify SOURCES_SHEET_ID and SOURCES_SHEET_TAB are set in Railway.
    """
    sheet_id_raw = (os.environ.get("SOURCES_SHEET_ID") or "").strip()
    tab = (os.environ.get("SOURCES_SHEET_TAB") or "").strip() or "sheet"
    return {
        "sources_configured": bool(sheet_id_raw),
        "sheet_id_set": bool(sheet_id_raw),
        "sheet_id_preview": f"{sheet_id_raw[:8]}...{sheet_id_raw[-4:]}" if len(sheet_id_raw) > 12 else ("(set)" if sheet_id_raw else "(not set)"),
        "sheet_tab": tab,
        "service_account_email": sources_sheet_service.get_service_account_email(),
    }


@router.get("/debug-source")
def debug_source(video_url: str) -> dict:
    """
    Debug source ID resolution without creating a card.
    Returns video_id, channel_id, channel_key, source_id, and any error.
    Example: GET /api/trello/debug-source?video_url=https://youtube.com/shorts/10-MmXMN1pg
    """
    result: dict = {
        "video_url": video_url,
        "video_id": None,
        "channel_id": None,
        "channel_key": None,
        "source_id": None,
        "sources_configured": sources_sheet_service.is_configured(),
        "service_account_email": sources_sheet_service.get_service_account_email(),
        "error": None,
    }
    try:
        vid = extract_video_id(video_url)
        result["video_id"] = vid
        if not vid:
            result["error"] = "Could not extract video_id from URL"
            return result
        channel_id = youtube_channel_service.get_channel_id_from_video(vid)
        result["channel_id"] = channel_id
        result["channel_key"] = channel_id if channel_id else video_url
        if not result["sources_configured"]:
            result["error"] = "SOURCES_SHEET_ID is not set"
            return result
        result["source_id"] = sources_sheet_service.get_or_create_source(result["channel_key"])
    except sources_sheet_service.SourcesSheetError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = str(e)
    return result


@router.post("/create-card", response_model=TrelloCreateResponse)
def create_trello_card(body: TrelloCreateRequest):
    """
    Create a Trello card by copying a template and filling in our content.

    This is part of the optional Trello module and can be disabled simply
    by not setting TRELLO_* environment variables.
    """
    try:
        voiceover_bytes: Optional[bytes] = None
        if (body.voiceover_mp3_base64 or "").strip():
            try:
                voiceover_bytes = base64.b64decode(body.voiceover_mp3_base64.strip(), validate=True)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid voiceover_mp3_base64 (must be base64).")

        # Resolve source_id from Sources sheet: one ID per channel (key by channel ID, fallback video URL).
        source_id: Optional[str] = body.source_id
        sources_configured = sources_sheet_service.is_configured()
        logger.info("Trello create-card: sources_configured=%s, body.source_id=%s", sources_configured, body.source_id)
        if source_id is None and sources_configured:
            try:
                video_id = extract_video_id(str(body.video_url))
                channel_id = youtube_channel_service.get_channel_id_from_video(video_id) if video_id else None
                channel_key = channel_id if channel_id else str(body.video_url)
                logger.info("Trello create-card: video_id=%s, channel_id=%s, channel_key=%s", video_id, channel_id, channel_key[:80] if channel_key else None)
                source_id = sources_sheet_service.get_or_create_source(channel_key)
                logger.info("Trello create-card: source_id=%s", source_id)
            except sources_sheet_service.SourcesSheetError as e:
                logger.warning("Sources sheet lookup failed (card will have no source_id): %s", e)
                source_id = None
        else:
            if not sources_configured:
                logger.warning("Trello create-card: SOURCES_SHEET_ID not set or empty in env — skipping source_id. Set it in Railway Variables and redeploy.")

        # Dry-run mode: only check whether the folder already existed, do NOT create a Trello card.
        if body.dry_run:
            existed = trello_service.check_voiceover_folder_exists(
                channel=body.channel,
                video_number=body.video_number,
            )
            return TrelloCreateResponse(
                card_url="",
                folder_existed=existed,
                voiceover_uploaded=False,
                voiceover_upload_error=None,
            )

        card_url, folder_existed, voiceover_uploaded, voiceover_upload_error = trello_service.create_card_from_template(
            video_url=str(body.video_url),
            source=body.source,
            title=body.translated_title,
            credits=body.credits,
            sentence_match=body.sentence_match,
            source_id=source_id,
            channel=body.channel,
            video_number=body.video_number,
            force_new_folder=body.force_new_folder,
            voiceover_mp3_bytes=voiceover_bytes,
            voiceover_filename=(body.voiceover_filename or "").strip() or None,
        )
        return TrelloCreateResponse(
            card_url=card_url,
            folder_existed=folder_existed,
            voiceover_uploaded=bool(voiceover_uploaded),
            voiceover_upload_error=voiceover_upload_error,
        )
    except trello_service.TrelloConfigError as e:
        logger.warning("Trello config error: %s", e)
        raise HTTPException(status_code=502, detail="Trello module is not configured.")
    except Exception as e:
        logger.exception("Failed to create Trello card")
        raise HTTPException(status_code=502, detail=f"Trello card creation failed: {e}")

