import threading
import time
import unittest
from collections.abc import Iterable
from unittest import mock

from claude_dictate.dictator import Dictator, TranscriptDeliveryError, UnsafeToType
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
        self.copy_to_clipboard = mock.Mock(return_value=True)

    def make(self, dictate, **options) -> Dictator:
        options.setdefault("max_hold_seconds", 5.0)
        options.setdefault("copy_to_clipboard", self.copy_to_clipboard)
        return Dictator(self.typer, lambda: self.keyboard, dictate, self.errors.append, **options)

    def test_press_then_release_types_the_transcript(self):
        dictator = self.make(dictate_returning("hello world"))
        self.assertEqual(dictator.press(), "recording")
        self.assertEqual(dictator.status(), "recording")
        self.assertEqual(dictator.release(), "released")
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["hello world"])
        self.copy_to_clipboard.assert_called_once_with("hello world")
        self.assertEqual(self.errors, [])
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

    def test_empty_or_whitespace_transcript_leaves_clipboard_and_typing_unchanged(self):
        for text in ("", " \t\n"):
            with self.subTest(text=text):
                dictator = self.make(dictate_returning(text))
                dictator.press()
                dictator.release()
                dictator.wait_until_idle(2)
                self.copy_to_clipboard.assert_not_called()
                self.assertEqual(self.typer.typed, [])
                self.assertEqual(self.errors, [])

    def test_original_text_is_copied_before_modifier_checks_and_typing(self):
        text = "  café 你好\nnext line\n"
        dictator = self.make(dictate_returning(text))
        events = mock.Mock()
        events.attach_mock(self.copy_to_clipboard, "copy")
        with (
            mock.patch.object(dictator, "_wait_for_modifiers_released", return_value=True) as safety,
            mock.patch.object(self.typer, "type_text") as type_text,
        ):
            events.attach_mock(safety, "safety")
            events.attach_mock(type_text, "type")
            dictator.press()
            dictator.release()
            dictator.wait_until_idle(2)
        self.assertEqual(events.mock_calls, [
            mock.call.copy(text), mock.call.safety(self.keyboard), mock.call.type(text),
        ])

    def test_failed_copy_still_types_and_reports_the_transcript(self):
        self.copy_to_clipboard.return_value = False
        dictator = self.make(dictate_returning("still typed"))
        dictator.press()
        dictator.release()
        dictator.wait_until_idle(2)
        self.copy_to_clipboard.assert_called_once_with("still typed")
        self.assertEqual(self.typer.typed, ["still typed"])
        self.assertEqual(len(self.errors), 1)
        self.assertIsInstance(self.errors[0], TranscriptDeliveryError)
        self.assertFalse(self.errors[0].clipboard_copied)
        self.assertEqual(self.errors[0].transcript, "still typed")
        self.assertIn("Typing completed", str(self.errors[0]))
        self.assertEqual(dictator.status(), "idle")

    def test_clipboard_writer_exception_does_not_prevent_typing(self):
        self.copy_to_clipboard.side_effect = OSError("clipboard unavailable")
        dictator = self.make(dictate_returning("still typed"))
        dictator.press()
        dictator.release()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, ["still typed"])
        self.assertEqual(len(self.errors), 1)
        self.assertFalse(self.errors[0].clipboard_copied)

    def test_typing_failure_retains_transcript_and_actual_clipboard_result(self):
        for copied in (True, False):
            with self.subTest(copied=copied):
                self.errors.clear()
                self.copy_to_clipboard.reset_mock()
                self.copy_to_clipboard.return_value = copied
                error = OSError("ydotool unavailable")
                dictator = self.make(dictate_returning("preserved"))
                with mock.patch.object(self.typer, "type_text", side_effect=error):
                    dictator.press()
                    dictator.release()
                    dictator.wait_until_idle(2)
                self.copy_to_clipboard.assert_called_once_with("preserved")
                self.assertEqual(len(self.errors), 1)
                self.assertIsInstance(self.errors[0], TranscriptDeliveryError)
                self.assertEqual(self.errors[0].transcript, "preserved")
                self.assertIs(self.errors[0].clipboard_copied, copied)
                self.assertIs(self.errors[0].__cause__, error)
                self.assertEqual(dictator.status(), "idle")

    def test_repeated_transcripts_are_copied_each_time(self):
        dictator = self.make(dictate_returning("repeat"))
        for _ in range(2):
            dictator.press()
            dictator.release()
            dictator.wait_until_idle(2)
        self.assertEqual(self.copy_to_clipboard.call_args_list, [
            mock.call("repeat"), mock.call("repeat"),
        ])

    def test_failed_copy_and_blocked_typing_report_one_error(self):
        self.keyboard = FakeKeyboard(available=False)
        self.copy_to_clipboard.return_value = False
        dictator = self.make(dictate_returning("kept in notification"))
        dictator.press()
        dictator.release()
        dictator.wait_until_idle(2)
        self.copy_to_clipboard.assert_called_once_with("kept in notification")
        self.assertEqual(self.typer.typed, [])
        self.assertEqual(len(self.errors), 1)
        self.assertIsInstance(self.errors[0], UnsafeToType)
        self.assertFalse(self.errors[0].clipboard_copied)

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
        self.copy_to_clipboard.assert_not_called()
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
        self.assertIsInstance(self.errors[0], UnsafeToType)
        self.assertEqual(self.errors[0].transcript, "kept safe")
        self.copy_to_clipboard.assert_called_once_with("kept safe")
        self.assertTrue(self.errors[0].clipboard_copied)

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
        self.assertIsInstance(self.errors[0], UnsafeToType)
        self.assertEqual(self.errors[0].transcript, "not typed blind")
        self.copy_to_clipboard.assert_called_once_with("not typed blind")
        self.assertTrue(self.errors[0].clipboard_copied)

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

    def test_without_readable_keyboards_release_works_but_nothing_is_typed(self):
        self.keyboard = FakeKeyboard(available=False)
        dictator = self.make(dictate_returning("preserved, not typed"))
        dictator.press()
        time.sleep(0.1)
        self.assertEqual(dictator.status(), "recording")
        dictator.release()
        dictator.wait_until_idle(2)
        self.assertEqual(self.typer.typed, [])
        self.assertIsInstance(self.errors[0], UnsafeToType)
        self.assertEqual(self.errors[0].transcript, "preserved, not typed")
        self.copy_to_clipboard.assert_called_once_with("preserved, not typed")
        self.assertTrue(self.errors[0].clipboard_copied)

    def test_unavailable_keyboard_refuses_typing_without_waiting_for_timeout(self):
        self.keyboard = FakeKeyboard(available=False)
        dictator = self.make(dictate_returning("fast refusal"), modifier_release_timeout=5.0)
        dictator.press()
        dictator.release()
        started = time.monotonic()
        dictator.wait_until_idle(2)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.typer.typed, [])
        self.assertIsInstance(self.errors[0], UnsafeToType)


if __name__ == "__main__":
    unittest.main()
