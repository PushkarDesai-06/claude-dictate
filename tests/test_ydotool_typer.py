import unittest
from unittest import mock

from claude_dictate.typers import TextTyper, YdotoolTyper
from claude_dictate.typers.ydotool import to_typeable_ascii


class ToTypeableAsciiTest(unittest.TestCase):
    def test_plain_ascii_is_unchanged(self):
        text = 'Hello, 100% (ok) "quoted" & done! @#$^*_+=|~ <a> [b] {c}'
        self.assertEqual(to_typeable_ascii(text), text)

    def test_curly_quotes_become_straight(self):
        self.assertEqual(to_typeable_ascii("it’s “fine”"), 'it\'s "fine"')

    def test_dashes_and_ellipsis(self):
        self.assertEqual(to_typeable_ascii("wait… a–b c—d"), "wait... a-b c-d")

    def test_accents_are_stripped(self):
        self.assertEqual(to_typeable_ascii("café, naïve, José"), "cafe, naive, Jose")

    def test_special_spaces_become_plain_spaces(self):
        self.assertEqual(to_typeable_ascii("a b c"), "a b c")

    def test_unmappable_characters_are_dropped(self):
        self.assertEqual(to_typeable_ascii("ok \U0001f600 你好 done"), "ok   done")

    def test_control_characters_are_dropped(self):
        self.assertEqual(to_typeable_ascii("a\x1b[31mb\x07c"), "a[31mbc")


class YdotoolTyperTest(unittest.TestCase):
    def test_is_a_text_typer(self):
        self.assertIsInstance(YdotoolTyper(), TextTyper)

    def test_interface_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            TextTyper()

    @mock.patch("claude_dictate.typers.ydotool.subprocess.run")
    def test_runs_ydotool_with_timing_and_normalized_text(self, run):
        YdotoolTyper(key_hold_ms=1, key_delay_ms=3).type_text("-it’s café")
        run.assert_called_once_with(
            ["ydotool", "type", "--key-hold", "1", "--key-delay", "3", "--", "-it's cafe"],
            check=True,
            capture_output=True,
        )

    @mock.patch("claude_dictate.typers.ydotool.subprocess.run")
    def test_skips_ydotool_when_nothing_is_typeable(self, run):
        YdotoolTyper().type_text("\U0001f600")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
