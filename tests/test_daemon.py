import subprocess
import unittest
from unittest import mock

from claude_dictate import daemon
from claude_dictate.dictator import UnsafeToType


@mock.patch("claude_dictate.daemon.notify")
@mock.patch("claude_dictate.daemon.subprocess.run")
class ReportErrorTest(unittest.TestCase):
    def test_unsafe_to_type_copies_transcript_and_says_so(self, run, notify):
        daemon.report_error(UnsafeToType("hello there"))
        run.assert_called_once()
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["wl-copy"])
        self.assertEqual(kwargs["input"], "hello there")
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        message = notify.call_args.args[0]
        self.assertIn("nothing was typed", message)
        self.assertIn("on your clipboard", message)

    def test_failed_copy_puts_transcript_in_notification(self, run, notify):
        run.side_effect = FileNotFoundError(2, "wl-copy")
        daemon.report_error(UnsafeToType("hello there"))
        message = notify.call_args.args[0]
        self.assertIn("Transcript: hello there", message)
        self.assertNotIn("clipboard", message)

    def test_hung_copy_puts_transcript_in_notification(self, run, notify):
        run.side_effect = subprocess.TimeoutExpired("wl-copy", 2)
        daemon.report_error(UnsafeToType("hello there"))
        self.assertIn("Transcript: hello there", notify.call_args.args[0])

    def test_other_errors_only_notify(self, run, notify):
        daemon.report_error(RuntimeError("push-to-talk did not start recording"))
        run.assert_not_called()
        notify.assert_called_once_with("push-to-talk did not start recording")


if __name__ == "__main__":
    unittest.main()
