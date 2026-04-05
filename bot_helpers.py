import re
from pathlib import Path


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def safe_title(info, file_path):
    title = (info.get("title") or "").strip()

    if not title or title.lower() in ["unknown", "na", "none"]:
        title = Path(file_path).stem

    return sanitize_filename(title)


def extract_url(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'(https?://[^\s]+)', text)
    return match.group(1) if match else None