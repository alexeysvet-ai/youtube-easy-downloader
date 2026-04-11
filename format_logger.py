# === FILE: format_logger.py ===
# === BUILD: 20260411-01-P0-LOG-FORMATS ===

from bot_core.utils import log


def log_available_formats(info: dict, max_entries: int = 50) -> None:
    """
    Logs available yt-dlp formats for diagnostics.
    Fail-safe: any error inside this function must not affect the main flow.
    """
    try:
        formats = info.get("formats", [])
        log(f"[FORMATS] total={len(formats)}")

        for idx, f in enumerate(formats[:max_entries]):
            format_id = f.get("format_id")
            ext = f.get("ext")
            height = f.get("height")
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")
            filesize = f.get("filesize")
            filesize_approx = f.get("filesize_approx")
            tbr = f.get("tbr")
            note = f.get("format_note")

            progressive = (
                vcodec not in (None, "none") and
                acodec not in (None, "none")
            )

            log(
                "[FORMAT] "
                f"id={format_id} "
                f"ext={ext} "
                f"height={height} "
                f"vcodec={vcodec} "
                f"acodec={acodec} "
                f"filesize={filesize} "
                f"filesize_approx={filesize_approx} "
                f"tbr={tbr} "
                f"note={note} "
                f"progressive={progressive}"
            )

        if len(formats) > max_entries:
            log(f"[FORMATS] truncated={len(formats) - max_entries}")

    except Exception as e:
        # Fail-safe: logging must never break the download flow
        log(f"[FORMATS LOG ERROR] {e}")