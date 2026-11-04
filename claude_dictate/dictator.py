import logging
import threading
import time
from collections.abc import Callable, Iterable
from typing import Protocol

from claude_dictate import clipboard, dictation
from claude_dictate.keyboard import KEY_SPACE, MODIFIER_KEYS, KeyStateUnavailable
from claude_dictate.typers import TextTyper

MAX_HOLD_SECONDS = 60.0
KEY_POLL_SECONDS = 0.02
MODIFIER_RELEASE_TIMEOUT = 10.0

log = logging.getLogger(__name__)


class KeyState(Protocol):
    """Physical key state. any_held raises KeyStateUnavailable when it cannot tell."""

    available: bool

    def any_held(self, keys: Iterable[int]) -> bool: ...

    def close(self) -> None: ...


class TranscriptDeliveryError(RuntimeError):
    def __init__(self, message: str, transcript: str, clipboard_copied: bool) -> None:
        super().__init__(message)
        self.transcript = transcript
        self.clipboard_copied = clipboard_copied


class UnsafeToType(TranscriptDeliveryError):
    def __init__(self, transcript: str, clipboard_copied: bool = False) -> None:
        super().__init__(
            "Could not confirm that modifier keys were released, so nothing was typed.",
            transcript,
            clipboard_copied,
        )


DictateFn = Callable[[threading.Event], str]
ErrorFn = Callable[[Exception], None]
ClipboardFn = Callable[[str], bool]
KeyStateFactory = Callable[[], KeyState]


class Dictator:
    """Turns press/release events into one dictation at a time, typed into the focused app.

    Release comes from whichever happens first: the release command, the hotkey no longer
    being physically held, or the max-hold watchdog. Typing waits until no modifier is
    physically held, so typed keys can never combine with a held modifier into a shortcut.
    Every nonempty transcript is copied before checking typing safety. When the key
    state is unknown, nothing is typed and the transcript goes to on_error.
    """

    def __init__(
        self,
        typer: TextTyper,
        keyboard_factory: KeyStateFactory,
        dictate: DictateFn = dictation.dictate,
        on_error: ErrorFn = lambda error: None,
        hotkey: int = KEY_SPACE,
        max_hold_seconds: float = MAX_HOLD_SECONDS,
        modifier_release_timeout: float = MODIFIER_RELEASE_TIMEOUT,
        copy_to_clipboard: ClipboardFn = clipboard.copy_to_clipboard,
    ) -> None:
        self._typer = typer
        self._keyboard_factory = keyboard_factory
        self._dictate = dictate
        self._on_error = on_error
        self._copy_to_clipboard = copy_to_clipboard
        self._hotkey = hotkey
        self._max_hold_seconds = max_hold_seconds
        self._modifier_release_timeout = modifier_release_timeout
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

    def _watch_hotkey(self, keyboard: KeyState, release: threading.Event) -> None:
        while not release.wait(KEY_POLL_SECONDS):
            try:
                hotkey_held = keyboard.any_held({self._hotkey})
            except KeyStateUnavailable as error:
                log.warning("stopped watching the hotkey (%s); relying on the release command", error)
                return
            if not hotkey_held:
                log.info("hotkey physically released")
                release.set()

    @staticmethod
    def _modifiers_maybe_held(keyboard: KeyState) -> bool:
        try:
            return keyboard.any_held(MODIFIER_KEYS)
        except KeyStateUnavailable:
            return True

    def _wait_for_modifiers_released(self, keyboard: KeyState) -> bool:
        deadline = time.monotonic() + self._modifier_release_timeout
        if self._modifiers_maybe_held(keyboard):
            log.info("waiting for modifier keys to be released before typing")
        while self._modifiers_maybe_held(keyboard):
            if time.monotonic() >= deadline:
                return False
            time.sleep(KEY_POLL_SECONDS)
        return True

    def _deliver(self, text: str, keyboard: KeyState) -> None:
        try:
            clipboard_copied = self._copy_to_clipboard(text)
        except Exception:
            log.exception("could not copy the transcript to the clipboard")
            clipboard_copied = False
        if not keyboard.available or not self._wait_for_modifiers_released(keyboard):
            raise UnsafeToType(text, clipboard_copied)
        try:
            self._typer.type_text(text)
        except Exception as error:
            raise TranscriptDeliveryError(
                f"Could not finish typing the transcript: {error}", text, clipboard_copied,
            ) from error
        if not clipboard_copied:
            raise TranscriptDeliveryError(
                "Typing completed, but the transcript could not be copied to the clipboard.",
                text,
                clipboard_copied,
            )

    def _run(self, release: threading.Event) -> None:
        keyboard: KeyState | None = None
        watchdog = threading.Timer(self._max_hold_seconds, release.set)
        watchdog.daemon = True
        try:
            watchdog.start()
            keyboard = self._keyboard_factory()
            if keyboard.available:
                threading.Thread(target=self._watch_hotkey, args=(keyboard, release), daemon=True).start()
            else:
                log.warning("not every keyboard is readable; relying on the release command alone")
            text = self._dictate(release)
            log.info("transcript: %r", text)
            if not text.strip():
                return
            self._deliver(text, keyboard)
        except Exception as error:
            log.exception("dictation failed")
            self._on_error(error)
        finally:
            watchdog.cancel()
            release.set()
            if keyboard is not None:
                keyboard.close()
            with self._lock:
                self._busy = False
                self._release = None
