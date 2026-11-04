import logging
import subprocess

log = logging.getLogger(__name__)


def copy_to_clipboard(text: str) -> bool:
    if not text.strip():
        return False
    try:
        subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=2,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        log.warning("could not copy the transcript to the clipboard")
        return False
