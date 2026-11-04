import threading
import unittest
from unittest import mock

from claude_dictate import dictation
from claude_dictate.transcript import InputState


class DictateHooksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        self.stopped = False

        session = mock.patch.object(dictation, "session").start()
        session.is_running.return_value = True
        session.push_to_talk_tick.side_effect = lambda: self.events.append("tick")

        transcript = mock.patch.object(dictation, "transcript").start()
        transcript.read_state.side_effect = lambda: InputState("hello", recording=not self.stopped)
        self.addCleanup(mock.patch.stopall)

    def started(self) -> None:
        self.events.append("started")

    def stopped_hook(self) -> None:
        self.stopped = True
        self.events.append("stopped")

    def run_dictation(self) -> str:
        release = threading.Event()
        release.set()
        return dictation.dictate(
            release,
            quiet_seconds=0.1,
            release_tail_seconds=0.0,
            on_recording_started=self.started,
            on_recording_stopped=self.stopped_hook,
        )

    def test_hooks_fire_once_each_in_order(self):
        self.assertEqual(self.run_dictation(), "hello")
        cues = [event for event in self.events if event != "tick"]
        self.assertEqual(cues, ["started", "stopped"])

    def test_stopped_hook_fires_only_after_push_to_talk_ticks_end(self):
        self.run_dictation()
        after_stop = self.events[self.events.index("stopped"):]
        self.assertNotIn("tick", after_stop)

    def test_no_hooks_fire_when_recording_never_starts(self):
        dictation.transcript.read_state.side_effect = lambda: InputState("", recording=False)
        with mock.patch.object(dictation, "RECORDING_START_TIMEOUT", 0.1):
            with self.assertRaises(dictation.VoiceNotActive):
                self.run_dictation()
        self.assertNotIn("started", self.events)
        self.assertNotIn("stopped", self.events)


if __name__ == "__main__":
    unittest.main()
