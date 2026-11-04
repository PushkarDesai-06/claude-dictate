import unittest
from unittest import mock

from claude_dictate import daemon
from claude_dictate.dictator import TranscriptDeliveryError, UnsafeToType


@mock.patch("claude_dictate.daemon.notify")
@mock.patch("claude_dictate.clipboard.copy_to_clipboard")
class ReportErrorTest(unittest.TestCase):
    def test_unsafe_to_type_reports_successful_copy_without_copying_again(self, copy, notify):
        daemon.report_error(UnsafeToType("hello there", clipboard_copied=True))
        copy.assert_not_called()
        message = notify.call_args.args[0]
        self.assertIn("nothing was typed", message)
        self.assertIn("on your clipboard", message)

    def test_failed_copy_puts_transcript_in_notification_without_retrying(self, copy, notify):
        daemon.report_error(UnsafeToType("hello there", clipboard_copied=False))
        copy.assert_not_called()
        message = notify.call_args.args[0]
        self.assertIn("Transcript: hello there", message)
        self.assertNotIn("on your clipboard", message)

    def test_typing_errors_report_actual_clipboard_result(self, copy, notify):
        for copied in (True, False):
            with self.subTest(copied=copied):
                daemon.report_error(TranscriptDeliveryError(
                    "Could not finish typing: ydotool failed", "café 你好", copied,
                ))
                message = notify.call_args.args[0]
                self.assertIn("Could not finish typing", message)
                if copied:
                    self.assertIn("on your clipboard", message)
                else:
                    self.assertIn("Transcript: café 你好", message)
                copy.assert_not_called()

    def test_successful_typing_with_failed_copy_reports_fallback(self, copy, notify):
        daemon.report_error(TranscriptDeliveryError(
            "Typing completed, but the transcript could not be copied to the clipboard.",
            "hello there", False,
        ))
        message = notify.call_args.args[0]
        self.assertIn("Typing completed", message)
        self.assertIn("Transcript: hello there", message)
        self.assertNotIn("on your clipboard", message)
        copy.assert_not_called()

    def test_other_errors_only_notify(self, copy, notify):
        daemon.report_error(RuntimeError("push-to-talk did not start recording"))
        copy.assert_not_called()
        notify.assert_called_once_with("push-to-talk did not start recording")


if __name__ == "__main__":
    unittest.main()
