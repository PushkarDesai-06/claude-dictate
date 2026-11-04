import threading
import unittest

from claude_dictate.dictator import Dictator
from claude_dictate.typers import TextTyper


class RecordingTyper(TextTyper):
    def __init__(self) -> None:
        self.typed: list[str] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)


def dictate_returning(text: str):
    def fake_dictate(release: threading.Event) -> str:
        release.wait(5)
        return text
    return fake_dictate


class DictatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.typer = RecordingTyper()
        self.errors: list[Exception] = []

    def make(self, dictate, max_hold_seconds: float = 5.0) -> Dictator:
        return Dictator(self.typer, dictate, self.errors.append, max_hold_seconds)

    def test_press_then_release_types_the_transcript(self):
        dictator = self.make(dictate_returning("hello world"))
        self.assertEqual(dictator.press(), "recording")
        self.assertEqual(dictator.status(), "recording")
        self.assertEqual(dictator.release(), "released")
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["hello world"])
        self.assertEqual(dictator.status(), "idle")

    def test_press_while_busy_is_rejected(self):
        dictator = self.make(dictate_returning("first"))
        dictator.press()
        self.assertEqual(dictator.press(), "busy")
        dictator.release()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["first"])

    def test_release_when_idle_is_ignored(self):
        dictator = self.make(dictate_returning("unused"))
        self.assertEqual(dictator.release(), "idle")

    def test_double_release_is_ignored(self):
        finishing = threading.Event()

        def slow_dictate(release: threading.Event) -> str:
            release.wait(5)
            finishing.wait(5)
            return "done"

        dictator = self.make(slow_dictate)
        dictator.press()
        self.assertEqual(dictator.release(), "released")
        self.assertEqual(dictator.status(), "finishing")
        self.assertEqual(dictator.release(), "idle")
        finishing.set()
        dictator.wait_until_idle(2)

    def test_empty_transcript_types_nothing(self):
        dictator = self.make(dictate_returning(""))
        dictator.press()
        dictator.release()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, [])

    def test_watchdog_releases_a_stuck_hold(self):
        dictator = self.make(dictate_returning("timed out"), max_hold_seconds=0.1)
        dictator.press()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["timed out"])

    def test_errors_are_reported_and_state_resets(self):
        def failing_dictate(release: threading.Event) -> str:
            raise RuntimeError("voice is off")

        dictator = self.make(failing_dictate)
        dictator.press()
        dictator.wait_until_idle(2)
        self.assertEqual([str(e) for e in self.errors], ["voice is off"])
        self.assertEqual(dictator.status(), "idle")
        self.assertEqual(dictator.press(), "recording")


if __name__ == "__main__":
    unittest.main()
