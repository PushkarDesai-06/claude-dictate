import logging
import subprocess
from pathlib import Path

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"
RECORDING_STARTED = SOUNDS_DIR / "recording-started.mp3"
RECORDING_STOPPED = SOUNDS_DIR / "recording-stopped.mp3"

log = logging.getLogger(__name__)


def play(sound: Path) -> None:
    """Start playing a sound and return immediately; a failure to play never interrupts dictation."""
    try:
        subprocess.Popen(
            ["pw-play", str(sound)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        log.warning("could not play %s: %s", sound.name, error)
