import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_LOCK = threading.Lock()
_VIDEO_ID_RE = r"^[A-Za-z0-9_-]{11}$"


def _store_path() -> Path:
    raw = (os.environ.get("PREPPED_VIDEO_STORE_PATH") or "").strip()
    if raw:
        return Path(raw)
    return Path("/tmp/sentence-match-prepped-video-ids-v1.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_video_id(video_id: str) -> str:
    from re import match

    candidate = (video_id or "").strip()
    if not match(_VIDEO_ID_RE, candidate):
        raise ValueError("Invalid video_id. Expected an 11-character YouTube video ID.")
    return candidate


def _read_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"videos": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"videos": {}}
    if not isinstance(parsed, dict):
        return {"videos": {}}
    videos = parsed.get("videos")
    if not isinstance(videos, dict):
        parsed["videos"] = {}
    return parsed


def _write_store(payload: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def get_status(video_id: str) -> Dict[str, Any]:
    normalized = _validate_video_id(video_id)
    with _LOCK:
        payload = _read_store()
        entry = payload.get("videos", {}).get(normalized)
        if not isinstance(entry, dict):
            return {
                "video_id": normalized,
                "already_prepped": False,
                "first_seen_at": None,
                "last_seen_at": None,
                "count": 0,
                "last_actor": None,
                "last_source_url": None,
            }
        return {
            "video_id": normalized,
            "already_prepped": True,
            "first_seen_at": entry.get("first_seen_at"),
            "last_seen_at": entry.get("last_seen_at"),
            "count": int(entry.get("count") or 0),
            "last_actor": entry.get("last_actor"),
            "last_source_url": entry.get("last_source_url"),
        }


def mark_prepped(video_id: str, actor: Optional[str] = None, source_url: Optional[str] = None) -> Dict[str, Any]:
    normalized = _validate_video_id(video_id)
    actor_value = (actor or "").strip() or None
    source_url_value = (source_url or "").strip() or None
    now = _utc_now()
    with _LOCK:
        payload = _read_store()
        videos = payload.setdefault("videos", {})
        current = videos.get(normalized)
        if not isinstance(current, dict):
            current = {
                "first_seen_at": now,
                "last_seen_at": now,
                "count": 1,
                "last_actor": actor_value,
                "last_source_url": source_url_value,
            }
        else:
            current["last_seen_at"] = now
            current["count"] = int(current.get("count") or 0) + 1
            current["last_actor"] = actor_value
            current["last_source_url"] = source_url_value
            if not current.get("first_seen_at"):
                current["first_seen_at"] = now
        videos[normalized] = current
        _write_store(payload)
        return {
            "video_id": normalized,
            "already_prepped": True,
            "first_seen_at": current.get("first_seen_at"),
            "last_seen_at": current.get("last_seen_at"),
            "count": int(current.get("count") or 0),
            "last_actor": current.get("last_actor"),
            "last_source_url": current.get("last_source_url"),
        }
