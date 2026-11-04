import unittest

from claude_dictate.transcript import InputBoxNotFound, parse_input_box

RULE = "\x1b[38;5;244m" + "─" * 40
FOOTER = "\x1b[39m  \x1b[38;5;246m[cryo@arch claude-dictate]\x1b[39m"


def screen(*box_rows: str) -> str:
    return "\n".join(["chat history", "", RULE, *box_rows, RULE, FOOTER, ""])


class ParseInputBoxTest(unittest.TestCase):
    def test_placeholder_reads_as_empty(self):
        styled = screen('\x1b[39m❯\xa0\x1b[2mTry "fix lint errors"\x1b[0m')
        self.assertEqual(parse_input_box(styled), "")

    def test_typed_text_matching_placeholder_is_kept(self):
        styled = screen('\x1b[39m❯\xa0Try "fix lint errors"')
        self.assertEqual(parse_input_box(styled), 'Try "fix lint errors"')

    def test_single_line(self):
        styled = screen("\x1b[39m❯\xa0Hello there, this is a voice mode test.")
        self.assertEqual(parse_input_box(styled), "Hello there, this is a voice mode test.")

    def test_wrapped_rows_are_joined_with_a_space(self):
        styled = screen(
            "\x1b[39m❯\xa0word01 word02 word03",
            "  word04 word05.   ",
        )
        self.assertEqual(parse_input_box(styled), "word01 word02 word03 word04 word05.")

    def test_level_meter_is_stripped_while_recording(self):
        styled = screen("\x1b[39m❯\xa0Hello, this is a long▇")
        self.assertEqual(parse_input_box(styled), "Hello, this is a long")

    def test_recording_with_no_words_yet(self):
        styled = screen("\x1b[39m❯\xa0▆")
        self.assertEqual(parse_input_box(styled), "")

    def test_missing_input_box_raises(self):
        with self.assertRaises(InputBoxNotFound):
            parse_input_box("just some text\nwith no rules\n")

    def test_uses_last_pair_of_rules(self):
        styled = "\n".join([RULE, "an old markdown block", RULE, "more history", screen("\x1b[39m❯\xa0final")])
        self.assertEqual(parse_input_box(styled), "final")


if __name__ == "__main__":
    unittest.main()
