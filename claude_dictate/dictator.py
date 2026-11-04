import logging
import threading
from collections.abc import Callable

from claude_dictate import dictation
from claude_dictate.typers import TextTyper

MAX_HOLD_SECONDS = 60.0

log = logging.getLogger(__name__)

DictateFn = Callable[[threading.Event], str]
ErrorFn = Callable[[Exception], None]


class Dictator:
    """Turns press/release events into one dictation at a time, typed into the focused app."""

    def __init__(
        self,
        typer: TextTyper,
        dictate: DictateFn = dictation.dictate,
        on_error: ErrorFn = lambda error: None,
        max_hold_seconds: float = MAX_HOLD_SECONDS,
    ) -> None:
        self._typer = typer
        self._dictate = dictate
        self._on_error = on_error
        self._max_hold_seconds = max_hold_seconds
        self._lock = threading.Lock()
        self._release: threading.Event | None = None
        self._busy = False
        self._worker: threading.Thread | None = None

    def press(self) -> str:
        with self._lock:
            if self._busy:
                return "busy"
            self._busy = True
            self._release = threading.Event()
            self._worker = threading.Thread(target=self._run, args=(self._release,), daemon=True)
            self._worker.start()
        return "recording"

    def release(self) -> str:
        with self._lock:
            if self._release is None or self._release.is_set():
                return "idle"
            self._release.set()
        return "released"

    def status(self) -> str:
        with self._lock:
            if not self._busy:
                return "idle"
            return "finishing" if self._release is not None and self._release.is_set() else "recording"

    def wait_until_idle(self, timeout: float | None = None) -> None:
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def _run(self, release: threading.Event) -> None:
        watchdog = threading.Timer(self._max_hold_seconds, release.set)
        watchdog.daemon = True
        try:
            watchdog.start()
            text = self._dictate(release)
            log.info("transcript: %r", text)
            if text:
                self._typer.type_text(text)
        except Exception as error:
            log.exception("dictation failed")
            self._on_error(error)
        finally:
            watchdog.cancel()
            with self._lock:
                self._busy = False
                self._release = None
