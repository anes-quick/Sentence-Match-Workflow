from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import prepped_videos


router = APIRouter(prefix="/prepped", tags=["prepped"])


class PreppedCheckRequest(BaseModel):
    video_id: str


class PreppedMarkRequest(BaseModel):
    video_id: str
    actor: Optional[str] = None
    source_url: Optional[str] = None


@router.post("/check", response_model=dict)
def check_prepped_status(body: PreppedCheckRequest) -> dict:
    try:
        return prepped_videos.get_status(body.video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to check prepped status.")


@router.post("/mark", response_model=dict)
def mark_prepped_status(body: PreppedMarkRequest) -> dict:
    try:
        return prepped_videos.mark_prepped(
            video_id=body.video_id,
            actor=body.actor,
            source_url=body.source_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to mark prepped status.")
