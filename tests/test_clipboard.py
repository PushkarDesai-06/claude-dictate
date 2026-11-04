import subprocess
import unittest
from unittest import mock

from claude_dictate.clipboard import copy_to_clipboard


@mock.patch("claude_dictate.clipboard.subprocess.run")
class CopyToClipboardTest(unittest.TestCase):
    def test_copies_original_unicode_text_with_a_timeout(self, run):
        text = "  café 你好\nnext line\n"
        self.assertTrue(copy_to_clipboard(text))
        run.assert_called_once_with(
            ["wl-copy"], input=text, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=2,
        )

    def test_empty_or_whitespace_text_leaves_clipboard_unchanged(self, run):
        for text in ("", " \n\t"):
            with self.subTest(text=text):
                self.assertFalse(copy_to_clipboard(text))
        run.assert_not_called()

    def test_missing_command_failure_and_timeout_return_false(self, run):
        for error in (
            FileNotFoundError(2, "wl-copy"),
            subprocess.CalledProcessError(1, "wl-copy"),
            subprocess.TimeoutExpired("wl-copy", 2),
        ):
            with self.subTest(error=error):
                run.side_effect = error
                self.assertFalse(copy_to_clipboard("hello"))


if __name__ == "__main__":
    unittest.main()
