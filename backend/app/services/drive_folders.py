import os
import io
from datetime import datetime
from typing import Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError


class DriveConfigError(RuntimeError):
    pass


_drive_service = None


def _get_drive_service():
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    sa_path = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not sa_path:
        raise DriveConfigError("GOOGLE_SERVICE_ACCOUNT_FILE is not set.")
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = service_account.Credentials.from_service_account_file(sa_path, scopes=scopes)
    _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


def _get_root_folder_id() -> str:
    rid = (os.environ.get("DRIVE_ROOT_FOLDER_ID") or "").strip()
    if not rid:
        raise DriveConfigError("DRIVE_ROOT_FOLDER_ID is not set.")
    return rid


def _ensure_child_folder(parent_id: str, name: str) -> Tuple[str, Optional[str]]:
    """Return (folder_id, webViewLink) for a child folder, creating if missing."""
    service = _get_drive_service()
    # Hinweis: wir gehen davon aus, dass der Name kein einfaches ' enthält.
    q = (
        f"'{parent_id}' in parents and "
        f"name = '{name}' and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = (
        service.files()
        .list(
            q=q,
            fields="files(id, name, webViewLink)",
            spaces="drive",
            pageSize=1,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = res.get("files") or []
    if files:
        f = files[0]
        return f["id"], f.get("webViewLink")

    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    new_folder = (
        service.files()
        .create(body=file_metadata, fields="id, webViewLink", supportsAllDrives=True)
        .execute()
    )
    return new_folder["id"], new_folder.get("webViewLink")


def ensure_voiceover_folder(
    channel: Optional[str],
    week: int,
    day: int,
    video_number: Optional[int],
    force_new: bool = False,
) -> Tuple[str, Optional[str], bool, str]:
    """
    Ensure the full folder structure exists and return (video_folder_id, webViewLink).

    Structure:
    /<Channel>
      /<MonthName>
        /KW<week>
          /CMNT-KW<week>-<day>
            /CMNT-KW<week>-<day>-<video_number>
              /Finished Video
    Voice-over Dateien liegen direkt im Video-Ordner, nicht in einem eigenen Unterordner.
    """
    root_id = _get_root_folder_id()
    today = datetime.utcnow().date()
    month_name = today.strftime("%B")  # English month name, e.g. March

    chan = (channel or "").strip() or "UnknownChannel"
    week_str = f"KW{week:02d}"
    day_prefix = f"CMNT-KW{week:02d}-{day:02d}"
    video_suffix = f"-{int(video_number)}" if video_number is not None else "-x"

    # Channel folder
    channel_id, _ = _ensure_child_folder(root_id, chan)
    # Month folder
    month_id, _ = _ensure_child_folder(channel_id, month_name)
    # KW folder
    kw_id, _ = _ensure_child_folder(month_id, week_str)
    # Day folder
    day_id, _ = _ensure_child_folder(kw_id, day_prefix)
    # Video folder (z.B. CMNT-KW11-10-1)
    video_folder_name = day_prefix + video_suffix

    service = _get_drive_service()
    existed = False

    if not force_new:
        # Versuchen, bestehenden Ordner zu finden, sonst neu anlegen.
        q = (
            f"'{day_id}' in parents and "
            f"name = '{video_folder_name}' and "
            "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        res = (
            service.files()
            .list(
                q=q,
                fields="files(id, name, webViewLink)",
                spaces="drive",
                pageSize=1,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )
        files = res.get("files") or []
        if files:
            f = files[0]
            video_id = f["id"]
            video_link = f.get("webViewLink")
            existed = True
        else:
            file_metadata = {
                "name": video_folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [day_id],
            }
            new_folder = (
                service.files()
                .create(body=file_metadata, fields="id, webViewLink", supportsAllDrives=True)
                .execute()
            )
            video_id = new_folder["id"]
            video_link = new_folder.get("webViewLink")
    else:
        # Immer neuen Ordner mit Suffix (1), (2), ... anlegen.
        base_name = video_folder_name
        idx = 1
        candidate = f"{base_name} ({idx})"
        while True:
            q = (
                f"'{day_id}' in parents and "
                f"name = '{candidate}' and "
                "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            )
            res = (
                service.files()
                .list(
                    q=q,
                    fields="files(id)",
                    spaces="drive",
                    pageSize=1,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            files = res.get("files") or []
            if not files:
                # Frei -> neuen Ordner mit diesem Namen anlegen.
                file_metadata = {
                    "name": candidate,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [day_id],
                }
                new_folder = (
                    service.files()
                    .create(body=file_metadata, fields="id, webViewLink", supportsAllDrives=True)
                    .execute()
                )
                video_id = new_folder["id"]
                video_link = new_folder.get("webViewLink")
                video_folder_name = candidate
                break
            idx += 1
    # Finished Video subfolder
    _finished_id, _ = _ensure_child_folder(video_id, "Finished Video")
    return video_id, video_link, existed, video_folder_name


def upload_voiceover_mp3(*, parent_folder_id: str, filename: str, mp3_bytes: bytes) -> str:
    """
    Upload an MP3 into the given Drive folder (same level as "Finished Video").

    Returns the uploaded file's webViewLink (if available).
    """
    if not parent_folder_id:
        raise ValueError("parent_folder_id is required")
    if not filename:
        filename = "voiceover.mp3"
    if not mp3_bytes:
        raise ValueError("mp3_bytes is empty")
    service = _get_drive_service()
    media = MediaIoBaseUpload(io.BytesIO(mp3_bytes), mimetype="audio/mpeg", resumable=False)
    file_metadata = {"name": filename, "parents": [parent_folder_id]}
    try:
        created = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        return created.get("webViewLink") or ""
    except HttpError as e:
        # Common in Workspace: service accounts often have no "My Drive" storage quota.
        msg = str(e)
        if "Service Accounts do not have storage quota" in msg or "storageQuotaExceeded" in msg:
            raise DriveConfigError(
                "Drive upload failed: service account has no storage quota. "
                "Move DRIVE_ROOT_FOLDER_ID into a Shared Drive and add the service account as a member, "
                "or use OAuth delegation."
            )
        raise

