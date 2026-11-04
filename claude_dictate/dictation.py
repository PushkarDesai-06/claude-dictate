import threading
import time

from claude_dictate import session, transcript

TICK_SECONDS = 0.03
POLL_SECONDS = 0.05
RECORDING_START_TIMEOUT = 2.0
QUIET_SECONDS = 1.0
RELEASE_TAIL_SECONDS = 0.3
FINALIZE_TIMEOUT = 8.0


class SessionNotRunning(RuntimeError):
    pass


class VoiceNotActive(RuntimeError):
    pass


class _PushToTalkHold:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick_until_stopped, daemon=True)

    def _tick_until_stopped(self) -> None:
        while not self._stop.is_set():
            session.push_to_talk_tick()
            self._stop.wait(TICK_SECONDS)

    def __enter__(self) -> "_PushToTalkHold":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join()


def _wait_for_recording(timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if transcript.read_state().recording:
            return
        time.sleep(POLL_SECONDS)
    raise VoiceNotActive("push-to-talk did not start recording; is /voice enabled?")


def _wait_for_final_text(quiet_seconds: float, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    last_state = transcript.read_state()
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        state = transcript.read_state()
        now = time.monotonic()
        if state != last_state:
            last_state, last_change = state, now
        elif not state.recording and now - last_change >= quiet_seconds:
            break
    return last_state.text


def dictate(
    release: threading.Event,
    quiet_seconds: float = QUIET_SECONDS,
    release_tail_seconds: float = RELEASE_TAIL_SECONDS,
) -> str:
    if not session.is_running():
        raise SessionNotRunning("claude-dictate session is not running; run claude-dictate-start")

    transcript.clear_input()
    with _PushToTalkHold():
        _wait_for_recording(RECORDING_START_TIMEOUT)
        release.wait()
        time.sleep(release_tail_seconds)

    text = _wait_for_final_text(quiet_seconds, FINALIZE_TIMEOUT)
    transcript.clear_input()
    return text


def dictate_for(seconds: float, **options: float) -> str:
    release = threading.Event()
    timer = threading.Timer(seconds, release.set)
    timer.start()
    try:
        return dictate(release, **options)
    finally:
        timer.cancel()
