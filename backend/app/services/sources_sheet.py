"""
Sources sheet: one SRC ID per channel. Key = channel ID (e.g. UC...) or fallback video URL.
Uses the same Google service account as Drive; requires Sheets API scope and SOURCES_SHEET_ID.
"""
import json
import os
import re
import time
import random
import string
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class SourcesSheetError(RuntimeError):
    pass


_sheets_service = None

# Sheet layout: A = channel_key (channel ID or video URL), B = source_id (SRC0001, ...). Row 1 = optional headers.
def _sheet_name() -> str:
    return (os.environ.get("SOURCES_SHEET_TAB") or "").strip() or "Sheet1"
_KEY_COL = "A"
_ID_COL = "B"


def get_service_account_email() -> Optional[str]:
    """
    Return the service account email (client_email) used for Sheets/Drive.
    Use this to verify the sheet is shared with the correct account.
    """
    json_str = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if json_str:
        try:
            info = json.loads(json_str)
            return (info.get("client_email") or "").strip() or None
        except Exception:
            return None
    sa_path = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not sa_path:
        return None
    try:
        with open(sa_path, "r") as f:
            info = json.load(f)
        return (info.get("client_email") or "").strip() or None
    except Exception:
        return None


def _get_sheets_service():
    """Use same credential env as Drive, with spreadsheets scope."""
    global _sheets_service
    if _sheets_service is not None:
        return _sheets_service

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    json_str = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if json_str:
        try:
            info = json.loads(json_str)
        except Exception as e:
            raise SourcesSheetError(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}")
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
    else:
        sa_path = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
        if not sa_path:
            raise SourcesSheetError(
                "SOURCES_SHEET_ID is set but GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE is not set."
            )
        creds = service_account.Credentials.from_service_account_file(sa_path, scopes=scopes)

    _sheets_service = build("sheets", "v4", credentials=creds)
    return _sheets_service


def _get_sheet_id() -> str:
    sid = (os.environ.get("SOURCES_SHEET_ID") or "").strip()
    if not sid:
        raise SourcesSheetError("SOURCES_SHEET_ID is not set.")
    return sid


def _normalize_channel_key(key: str) -> str:
    """Canonical form for lookup: strip whitespace. For URLs also lowercase and no trailing slash."""
    k = (key or "").strip()
    if not k:
        return k
    if "youtube.com" in k.lower() or "youtu.be" in k.lower():
        k = k.lower()
        if k.endswith("/"):
            k = k[:-1]
    return k


def _next_source_id(existing_ids: list[str]) -> str:
    """Return next SRC number, e.g. SRC0001, SRC0002, ... (4-digit zero-padded)."""
    max_n = 0
    pattern = re.compile(r"^SRC(\d+)$", re.IGNORECASE)
    for sid in existing_ids:
        if not isinstance(sid, str):
            continue
        m = pattern.match(sid.strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"SRC{max_n + 1:04d}"


def get_or_create_source(channel_key: str) -> str:
    """
    Look up or create a source ID for the given channel key.
    channel_key should be YouTube channel ID (e.g. UC...) so one ID per channel;
    if only video URL is available, it is used as key (one ID per video in that case).
    Returns e.g. SRC0001, SRC0002.
    """
    sheet_id = _get_sheet_id()
    key = _normalize_channel_key(channel_key)
    if not key:
        raise SourcesSheetError("channel_key is empty after normalizing.")

    service = _get_sheets_service()
    range_ = f"{_sheet_name()}!{_KEY_COL}:{_ID_COL}"

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=range_,
        ).execute()
        rows = result.get("values") or []
    except HttpError as e:
        msg = (e.content or str(e)).decode("utf-8") if hasattr(e, "content") and e.content else str(e)
        if "404" in msg or "not found" in msg.lower():
            raise SourcesSheetError(
                f"Sources sheet not found. Create a Google Sheet, share it with the service account (Editor), "
                f"and set SOURCES_SHEET_ID to the sheet ID from the URL. Details: {msg}"
            )
        if "403" in msg or "permission" in msg.lower() or "Access Not Configured" in msg or "has not been used" in msg:
            hint = "Share the sheet with the service account email (Editor)."
            if "Access Not Configured" in msg or "has not been used" in msg:
                hint = "Enable 'Google Sheets API' in Google Cloud Console for this project (APIs & Services → Library → Google Sheets API)."
            raise SourcesSheetError(
                f"No permission to read Sources sheet (spreadsheetId={sheet_id}). {hint} Raw: {msg[:300]}"
            )
        raise SourcesSheetError(f"Sources sheet error: {msg}")

    # First row may be headers
    if rows and rows[0] and (rows[0][0] or "").strip().lower() == "source_key":
        data_rows = rows[1:]
    else:
        data_rows = rows

    existing_ids = []
    for row in data_rows:
        if len(row) < 2:
            continue
        row_key = (row[0] or "").strip()
        row_id = (row[1] or "").strip()
        if row_key == key:
            if row_id.upper().startswith("SRC"):
                return row_id
            # malformed id; treat as new and assign next
            break
        if row_id:
            existing_ids.append(row_id)

    # Not found: append new row
    new_id = _next_source_id(existing_ids)
    append_range = f"{_sheet_name()}!{_KEY_COL}:{_ID_COL}"
    body = {"values": [[key, new_id]]}

    try:
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=append_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
    except HttpError as e:
        msg = (e.content or str(e)).decode("utf-8") if hasattr(e, "content") and e.content else str(e)
        if "403" in msg or "permission" in msg.lower() or "Access Not Configured" in msg:
            hint = "Share the sheet with the service account email (Editor)."
            if "Access Not Configured" in msg or "has not been used" in msg:
                hint = "Enable 'Google Sheets API' in Google Cloud Console (APIs & Services → Library)."
            raise SourcesSheetError(f"No permission to write to Sources sheet. {hint} Raw: {msg[:300]}")
        raise SourcesSheetError(f"Sources sheet append error: {msg}")

    return new_id


def is_configured() -> bool:
    """True if SOURCES_SHEET_ID is set (and we can try to use the sheet)."""
    return bool((os.environ.get("SOURCES_SHEET_ID") or "").strip())


def test_write_to_sheet() -> str:
    """
    Append one test row to the sheet to verify write access.
    Row: A = "TEST_WRITE", B = "ok_<timestamp>_<random>".
    Returns a success message; raises SourcesSheetError on failure.
    You can delete the test row from the sheet after.
    """
    sheet_id = _get_sheet_id()
    service = _get_sheets_service()
    value_b = f"ok_{int(time.time())}_{''.join(random.choices(string.ascii_lowercase, k=6))}"
    append_range = f"{_sheet_name()}!{_KEY_COL}:{_ID_COL}"
    body = {"values": [["TEST_WRITE", value_b]]}
    try:
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=append_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        return f"Wrote test row: TEST_WRITE | {value_b}"
    except HttpError as e:
        msg = (e.content or str(e)).decode("utf-8") if hasattr(e, "content") and e.content else str(e)
        if "403" in msg or "permission" in msg.lower():
            raise SourcesSheetError(f"No permission to write. Share the sheet with the service account (Editor). Raw: {msg[:200]}")
        raise SourcesSheetError(f"Sheet write failed: {msg[:300]}")
