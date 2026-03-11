import re
from typing import Optional

# Match @username (handle: @ plus letters, numbers, underscore, dot)
AT_HANDLE_RE = re.compile(r"@([a-zA-Z0-9_.]+)")

DEFAULT_CREDITS = "@Respected Owner"

# Common email domains to exclude (e.g. @gmail.com in "contact@gmail.com")
EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "outlook.com",
    "hotmail.com", "hotmail.co.uk", "icloud.com", "live.com", "mail.com",
    "aol.com", "protonmail.com", "zoho.com", "yandex.com", "gmx.com", "gmx.de",
    "web.de", "t-online.de", "orange.fr", "free.fr", "laposte.net", "outlook.de",
    "outlook.fr", "me.com", "msn.com", "ymail.com", "rocketmail.com", "btinternet.com",
    "virginmedia.com", "sky.com", "talktalk.net", "ntlworld.com", "blueyonder.co.uk",
})


def _is_email_domain(part: str) -> bool:
    """True if the part after @ is a known email domain (e.g. gmail.com)."""
    return part.lower() in EMAIL_DOMAINS


def extract_credits(description: Optional[str]) -> str:
    """Extract only @usernames from video description. Multiple handles joined with ' & '. Default @Respected Owner if none found."""
    if not description or not description.strip():
        return DEFAULT_CREDITS
    text = description.strip()
    seen = set()
    handles = []
    for m in AT_HANDLE_RE.finditer(text):
        part = m.group(1)
        if _is_email_domain(part):
            continue
        handle = "@" + part
        if handle.lower() not in seen:
            seen.add(handle.lower())
            handles.append(handle)
    if handles:
        return " & ".join(handles)
    return DEFAULT_CREDITS
