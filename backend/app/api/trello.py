import logging
import base64
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.services import trello as trello_service
from app.services import sources_sheet as sources_sheet_service

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

        # Resolve source_id from Sources sheet when not provided (by video_url).
        source_id: Optional[str] = body.source_id
        if source_id is None and sources_sheet_service.is_configured():
            try:
                source_id = sources_sheet_service.get_or_create_source(str(body.video_url))
            except sources_sheet_service.SourcesSheetError as e:
                logger.warning("Sources sheet lookup failed (card will have no source_id): %s", e)
                source_id = None

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

