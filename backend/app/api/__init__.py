import os

from fastapi import APIRouter

from .process import router as process_router
from .voiceover import router as voiceover_router
from .trello import router as trello_router

router = APIRouter()
router.include_router(process_router)
router.include_router(voiceover_router)

# Optional Trello module – only enable routes when configured.
if (
    (os.environ.get("TRELLO_API_KEY") or "").strip()
    and (os.environ.get("TRELLO_TOKEN") or "").strip()
    and (os.environ.get("TRELLO_TEMPLATE_CARD_ID") or "").strip()
):
    router.include_router(trello_router)

@router.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok"}
