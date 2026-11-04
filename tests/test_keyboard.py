import tempfile
import unittest
from pathlib import Path
from unittest import mock

from claude_dictate.keyboard import (
    KEY_SPACE,
    KeyStateUnavailable,
    PhysicalKeyboard,
    keyboard_device_paths,
)

KEY_LEFTMETA = 125
EV_KEYBOARD_WITH_REPEAT = "120013"
EV_KEYBOARD_NO_REPEAT = "3"


def key_bitmap(*keys: int) -> str:
    value = sum(1 << key for key in keys)
    words = []
    while value:
        words.append(f"{value & (2**64 - 1):x}")
        value >>= 64
    return " ".join(reversed(words)) or "0"


def device_block(name: str, sysfs: str, event: str, ev: str, keys: str) -> str:
    return "\n".join([
        "I: Bus=0003 Vendor=0001 Product=0001 Version=0001",
        f'N: Name="{name}"',
        f"S: Sysfs={sysfs}",
        f"H: Handlers=sysrq kbd {event} leds",
        f"B: EV={ev}",
        f"B: KEY={keys}",
    ])


class KeyboardDiscoveryTest(unittest.TestCase):
    def discover(self, *blocks: str) -> list[str]:
        with tempfile.NamedTemporaryFile("w", suffix="devices") as devices:
            devices.write("\n\n".join(blocks) + "\n")
            devices.flush()
            return [str(path) for path in keyboard_device_paths(Path(devices.name))]

    def test_physical_keyboard_is_found(self):
        found = self.discover(device_block(
            "AT Translated Set 2 keyboard", "/devices/platform/i8042/serio0/input/input3",
            "event3", EV_KEYBOARD_WITH_REPEAT, key_bitmap(KEY_SPACE, KEY_LEFTMETA),
        ))
        self.assertEqual(found, ["/dev/input/event3"])

    def test_virtual_keyboard_is_skipped_even_with_repeat_and_space(self):
        found = self.discover(device_block(
            "remote-touchpad-keyboard", "/devices/virtual/input/input40",
            "event20", EV_KEYBOARD_WITH_REPEAT, key_bitmap(KEY_SPACE),
        ))
        self.assertEqual(found, [])

    def test_device_without_key_repeat_is_skipped(self):
        found = self.discover(device_block(
            "Some Consumer Control", "/devices/pci0000:00/usb1/input/input12",
            "event9", EV_KEYBOARD_NO_REPEAT, key_bitmap(KEY_SPACE),
        ))
        self.assertEqual(found, [])

    def test_device_without_space_is_skipped(self):
        found = self.discover(device_block(
            "Power Button", "/devices/LNXSYSTM:00/input/input1",
            "event1", EV_KEYBOARD_WITH_REPEAT, key_bitmap(116),
        ))
        self.assertEqual(found, [])


def ioctl_reporting(*held: int):
    def fake_ioctl(fd, request, state):
        for key in held:
            state[key // 8] |= 1 << (key % 8)
        return 0
    return fake_ioctl


@mock.patch("claude_dictate.keyboard.os.close")
@mock.patch("claude_dictate.keyboard.os.open", side_effect=[10, 11])
class PhysicalKeyboardTest(unittest.TestCase):
    paths = [Path("/dev/input/event3"), Path("/dev/input/event4")]

    def test_reports_held_keys_across_keyboards(self, _open, _close):
        with mock.patch("claude_dictate.keyboard.fcntl.ioctl", side_effect=ioctl_reporting(KEY_SPACE)):
            keyboard = PhysicalKeyboard(self.paths)
            self.assertTrue(keyboard.available)
            self.assertEqual(keyboard.held_keys(), {KEY_SPACE})
            self.assertTrue(keyboard.any_held({KEY_SPACE}))
            self.assertFalse(keyboard.any_held({KEY_LEFTMETA}))

    def test_failed_read_is_unknown_not_released(self, _open, _close):
        with mock.patch("claude_dictate.keyboard.fcntl.ioctl", side_effect=OSError(19, "No such device")):
            keyboard = PhysicalKeyboard(self.paths)
            with self.assertRaises(KeyStateUnavailable):
                keyboard.any_held({KEY_SPACE})

    def test_one_unopenable_keyboard_makes_state_unavailable(self, os_open, _close):
        os_open.side_effect = [10, PermissionError(13, "Permission denied")]
        keyboard = PhysicalKeyboard(self.paths)
        self.assertFalse(keyboard.available)
        with self.assertRaises(KeyStateUnavailable):
            keyboard.held_keys()

    def test_no_keyboards_is_unavailable(self, _open, _close):
        self.assertFalse(PhysicalKeyboard([]).available)


if __name__ == "__main__":
    unittest.main()
