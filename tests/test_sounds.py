import subprocess
import unittest
from pathlib import Path
from unittest import mock

from claude_dictate import sounds


class SoundsTest(unittest.TestCase):
    def test_bundled_sounds_exist(self):
        self.assertTrue(sounds.RECORDING_STARTED.is_file())
        self.assertTrue(sounds.RECORDING_STOPPED.is_file())

    @mock.patch("claude_dictate.sounds.subprocess.Popen")
    def test_play_starts_pw_play_detached_without_waiting(self, popen):
        sounds.play(Path("/x/cue.wav"))
        popen.assert_called_once_with(
            ["pw-play", "/x/cue.wav"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        popen.return_value.wait.assert_not_called()

    @mock.patch("claude_dictate.sounds.subprocess.Popen", side_effect=FileNotFoundError(2, "pw-play"))
    def test_missing_player_does_not_raise(self, _popen):
        sounds.play(Path("/x/cue.wav"))


if __name__ == "__main__":
    unittest.main()
