import threading
import time
import unittest
from collections.abc import Iterable

from claude_dictate.dictator import Dictator, ModifiersStillHeld
from claude_dictate.keyboard import KEY_SPACE, KeyStateUnavailable
from claude_dictate.typers import TextTyper

KEY_LEFTMETA = 125


class RecordingTyper(TextTyper):
    def __init__(self) -> None:
        self.typed: list[str] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)


class FakeKeyboard:
    def __init__(self, held: Iterable[int] = (), available: bool = True) -> None:
        self.held = set(held)
        self.available = available
        self.unreadable = False
        self.closed = False

    def any_held(self, keys: Iterable[int]) -> bool:
        if self.unreadable:
            raise KeyStateUnavailable("device went away")
        return not self.held.isdisjoint(keys)

    def close(self) -> None:
        self.closed = True


def dictate_returning(text: str):
    def fake_dictate(release: threading.Event) -> str:
        release.wait(5)
        return text
    return fake_dictate


class DictatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.typer = RecordingTyper()
        self.errors: list[Exception] = []
        self.keyboard = FakeKeyboard(held={KEY_SPACE})

    def make(self, dictate, **options) -> Dictator:
        options.setdefault("max_hold_seconds", 5.0)
        return Dictator(self.typer, lambda: self.keyboard, dictate, self.errors.append, **options)

    def test_press_then_release_types_the_transcript(self):
        dictator = self.make(dictate_returning("hello world"))
        self.assertEqual(dictator.press(), "recording")
        self.assertEqual(dictator.status(), "recording")
        self.assertEqual(dictator.release(), "released")
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["hello world"])
        self.assertEqual(dictator.status(), "idle")
        self.assertTrue(self.keyboard.closed)

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

    def test_letting_go_of_the_hotkey_releases_without_a_release_command(self):
        dictator = self.make(dictate_returning("physical release"))
        dictator.press()
        time.sleep(0.1)
        self.assertEqual(dictator.status(), "recording")
        self.keyboard.held.discard(KEY_SPACE)
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["physical release"])

    def test_typing_waits_for_modifiers_to_be_released(self):
        self.keyboard.held = {KEY_LEFTMETA}
        dictator = self.make(dictate_returning("after super"))
        dictator.press()
        time.sleep(0.2)
        self.assertEqual(self.typer.typed, [])
        self.keyboard.held.clear()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["after super"])

    def test_modifier_held_too_long_types_nothing_and_reports_transcript(self):
        self.keyboard.held = {KEY_LEFTMETA}
        dictator = self.make(dictate_returning("kept safe"), modifier_release_timeout=0.1)
        dictator.press()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, [])
        self.assertIsInstance(self.errors[0], ModifiersStillHeld)
        self.assertEqual(self.errors[0].transcript, "kept safe")

    def test_unreadable_keys_during_hold_do_not_release_early(self):
        dictator = self.make(dictate_returning("still recording"))
        dictator.press()
        time.sleep(0.05)
        self.keyboard.unreadable = True
        time.sleep(0.1)
        self.assertEqual(dictator.status(), "recording")
        dictator.release()
        dictator.wait_until_idle(2)

    def test_unreadable_keys_before_typing_type_nothing_and_report_transcript(self):
        dictator = self.make(dictate_returning("not typed blind"), modifier_release_timeout=0.1)
        dictator.press()
        self.keyboard.unreadable = True
        dictator.release()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, [])
        self.assertIsInstance(self.errors[0], ModifiersStillHeld)
        self.assertEqual(self.errors[0].transcript, "not typed blind")

    def test_keyboard_discovery_failure_reports_error_and_frees_the_dictator(self):
        def broken_factory():
            raise OSError(2, "No such file or directory: '/proc/bus/input/devices'")

        dictator = Dictator(self.typer, broken_factory, dictate_returning("x"), self.errors.append)
        dictator.press()
        dictator.wait_until_idle(2)
        self.assertIsInstance(self.errors[0], OSError)
        self.assertEqual(dictator.status(), "idle")
        self.assertEqual(dictator.press(), "recording")
        dictator.release()
        dictator.wait_until_idle(2)

    def test_without_readable_keyboards_the_release_command_still_works(self):
        self.keyboard = FakeKeyboard(available=False)
        dictator = self.make(dictate_returning("fallback"))
        dictator.press()
        time.sleep(0.1)
        self.assertEqual(dictator.status(), "recording")
        dictator.release()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["fallback"])


if __name__ == "__main__":
    unittest.main()
