import os
from datetime import datetime
from typing import Optional

import httpx

from . import drive_folders


TRELLO_API_BASE = "https://api.trello.com/1"


class TrelloConfigError(RuntimeError):
    pass


def _get_auth_params() -> dict:
    key = (os.environ.get("TRELLO_API_KEY") or "").strip()
    token = (os.environ.get("TRELLO_TOKEN") or "").strip()
    if not key or not token:
        raise TrelloConfigError("Trello API key/token not configured.")
    return {"key": key, "token": token}


def _get_template_card_id() -> str:
    cid = (os.environ.get("TRELLO_TEMPLATE_CARD_ID") or "").strip()
    if not cid:
        raise TrelloConfigError("TRELLO_TEMPLATE_CARD_ID is not set.")
    return cid


def _get_board_id() -> str:
    bid = (os.environ.get("TRELLO_BOARD_ID") or "").strip()
    if not bid:
        raise TrelloConfigError("TRELLO_BOARD_ID is not set.")
    return bid


def _build_description(
    *,
    video_url: str,
    source: Optional[str],
    title: str,
    credits: Optional[str],
    sentence_match: str,
) -> str:
    """
    Build the Trello card description in the agreed format.

    link - <video_url>
    Source - <source>          (uploader / channel of inspo video)
    title - <German title>
    cr - <credits string>
    sentence match -
    ```trello
    ...
    ```
    """
    src = (source or "").strip()
    cr = (credits or "").strip()
    # For now, if explicit source is empty, fall back to credits.
    if not src and cr:
        src = cr
    lines = [
        f"link - {video_url or ''}",
        "",
        f"Source - {src or ''}",
        "",
        f"title - {title or ''}",
        "",
        f"cr - {cr or ''}",
        "",
        "sentence match -",
        "```trello",
        (sentence_match or "").strip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def create_card_from_template(
    *,
    video_url: str,
    source: Optional[str],
    title: str,
    credits: Optional[str],
    sentence_match: str,
    channel: Optional[str] = None,
    video_number: Optional[int] = None,
    force_new_folder: bool = False,
    voiceover_mp3_bytes: Optional[bytes] = None,
    voiceover_filename: Optional[str] = None,
) -> tuple[str, bool, bool, Optional[str]]:
    """
    Copy the template card and fill in name + description.

    Returns the URL of the created Trello card.
    """
    params = _get_auth_params()
    template_id = _get_template_card_id()
    board_id = _get_board_id()

    # First, find the target list.
    with httpx.Client(timeout=30.0) as client:
        # Prefer the list named "Info" on the configured board.
        lr = client.get(
            f"{TRELLO_API_BASE}/boards/{board_id}/lists",
            params={**params, "fields": "name"},
        )
        lr.raise_for_status()
        lists = lr.json() or []
        list_id: Optional[str] = None
        for lst in lists:
            if isinstance(lst, dict) and (lst.get("name") or "").strip().lower() == "info":
                list_id = lst.get("id")
                break

        # Fallback: fetch the template card to reuse its list if "Info" is not found.
        r = client.get(
            f"{TRELLO_API_BASE}/cards/{template_id}",
            params={**params, "fields": "idList"},
        )
        r.raise_for_status()
        data = r.json()
        if not list_id:
            list_id = data.get("idList")
        full_card_id = data.get("id")
        if not list_id:
            raise RuntimeError("Could not determine list for template card.")
        if not full_card_id:
            raise RuntimeError("Could not determine full id for template card.")

        # Card name pattern:
        # ("Channel name") CMNT-KW<calendar week>-<day>-<number>
        # Channel and video_number are provided by the VA via the UI.
        today = datetime.utcnow().date()
        week = today.isocalendar().week  # calendar week
        day = today.day
        chan = (channel or "").strip()
        if chan:
            chan_part = f"({chan}) "
        else:
            chan_part = "() "
        num_part = f"{int(video_number)}" if video_number is not None else ""
        name = f"{chan_part}CMNT-KW{week:02d}-{day:02d}-{num_part}"

        # Try to ensure die Drive-Ordnerstruktur und den Video-Ordner-Link.
        video_link: Optional[str] = None
        folder_existed = False
        video_folder_name: Optional[str] = None
        voiceover_uploaded = False
        voiceover_upload_error: Optional[str] = None
        try:
            video_folder_id, video_link, folder_existed, video_folder_name = drive_folders.ensure_voiceover_folder(
                channel=channel,
                week=week,
                day=day,
                video_number=video_number,
                force_new=force_new_folder,
            )
            if voiceover_mp3_bytes:
                try:
                    drive_folders.upload_voiceover_mp3(
                        parent_folder_id=video_folder_id,
                        filename=(voiceover_filename or "voiceover.mp3"),
                        mp3_bytes=voiceover_mp3_bytes,
                    )
                    voiceover_uploaded = True
                except drive_folders.DriveConfigError as e:
                    voiceover_upload_error = str(e)
                except Exception:
                    # Upload failures shouldn't block card creation.
                    voiceover_upload_error = "Drive upload failed (unknown error)."
        except Exception:
            # Drive-Konfig / Fehler sollen die Trello-Card-Erstellung nicht blockieren.
            video_link = None
            video_folder_name = None

        desc = _build_description(
            video_url=video_url,
            source=source,
            title=title,
            credits=credits,
            sentence_match=sentence_match,
        )

        create_params = {
            **params,
            "idList": list_id,
            "idCardSource": full_card_id,
            "keepFromSource": "all",
            "name": name,
            "desc": desc,
        }
        cr = client.post(f"{TRELLO_API_BASE}/cards", params=create_params)
        if cr.status_code >= 400:
            # Surface Trello's error message to help debugging.
            try:
                err = cr.json()
            except Exception:
                err = cr.text
            raise RuntimeError(f"Trello create card failed: {cr.status_code} - {err}")
        card = cr.json()
        card_url = card.get("url")
        card_id = card.get("id")
        if not card_url or not card_id:
            raise RuntimeError(f"Trello did not return card URL or id. Raw: {card}")

        # Falls wir einen Drive-Video-Ordner-Link haben, als Anhang an die Card hängen,
        # damit er im unteren Bereich der Karte sichtbar ist.
        if video_link:
            try:
                attach_params = {
                    **params,
                    "url": video_link,
                    "name": video_folder_name or "Drive: CMNT Folder",
                }
                client.post(
                    f"{TRELLO_API_BASE}/cards/{card_id}/attachments",
                    params=attach_params,
                )
            except Exception:
                # Anhang-Fehler ignorieren – Card existiert trotzdem.
                pass

        return card_url, (folder_existed and not force_new_folder), voiceover_uploaded, voiceover_upload_error

