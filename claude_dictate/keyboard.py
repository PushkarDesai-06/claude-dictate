"""Query which keys are physically held, straight from the evdev keyboards.

Only the instantaneous key state is read (EVIOCGKEY); the event stream is never consumed.
Any keyboard that cannot be read makes the key state unknown, never "released".
"""

import fcntl
import logging
import os
import re
from collections.abc import Iterable
from pathlib import Path

KEY_SPACE = 57
MODIFIER_KEYS = frozenset({
    29, 97,    # ctrl
    42, 54,    # shift
    56, 100,   # alt
    125, 126,  # super
})

_KEY_MAX = 0x2FF
_KEY_STATE_BYTES = _KEY_MAX // 8 + 1
_IOC_READ = 2
_EVIOCGKEY = (_IOC_READ << 30) | (_KEY_STATE_BYTES << 16) | (ord("E") << 8) | 0x18
_EV_REP_BIT = 0x14
_VIRTUAL_SYSFS_PREFIX = "/devices/virtual/"
_DEVICES_FILE = Path("/proc/bus/input/devices")

log = logging.getLogger(__name__)


class KeyStateUnavailable(RuntimeError):
    pass


def _key_bitmap(hex_words: str) -> int:
    return int("".join(word.rjust(16, "0") for word in hex_words.split()), 16)


def keyboard_device_paths(devices_file: Path = _DEVICES_FILE) -> list[Path]:
    paths = []
    for block in devices_file.read_text().strip().split("\n\n"):
        sysfs = re.search(r"^S: Sysfs=(\S+)", block, re.M)
        ev = re.search(r"^B: EV=(\w+)", block, re.M)
        keys = re.search(r"^B: KEY=([\w ]+)", block, re.M)
        event = re.search(r"^H: Handlers=.*\b(event\d+)\b", block, re.M)
        if not (sysfs and ev and keys and event):
            continue
        if sysfs.group(1).startswith(_VIRTUAL_SYSFS_PREFIX):
            continue
        repeats = int(ev.group(1), 16) >> _EV_REP_BIT & 1
        has_space = _key_bitmap(keys.group(1)) >> KEY_SPACE & 1
        if repeats and has_space:
            paths.append(Path("/dev/input") / event.group(1))
    return paths


class PhysicalKeyboard:
    def __init__(self, paths: Iterable[Path] | None = None) -> None:
        self._fds: list[int] = []
        self._every_keyboard_opened = True
        for path in keyboard_device_paths() if paths is None else paths:
            try:
                self._fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
            except OSError as error:
                log.warning("cannot read %s: %s", path, error)
                self._every_keyboard_opened = False

    @property
    def available(self) -> bool:
        return bool(self._fds) and self._every_keyboard_opened

    def held_keys(self) -> set[int]:
        if not self.available:
            raise KeyStateUnavailable("not every keyboard could be opened")
        held = set()
        for fd in self._fds:
            state = bytearray(_KEY_STATE_BYTES)
            try:
                fcntl.ioctl(fd, _EVIOCGKEY, state)
            except OSError as error:
                raise KeyStateUnavailable(f"could not read key state: {error}") from error
            for index, byte in enumerate(state):
                if byte:
                    held.update(index * 8 + bit for bit in range(8) if byte >> bit & 1)
        return held

    def any_held(self, keys: Iterable[int]) -> bool:
        return not self.held_keys().isdisjoint(keys)

    def close(self) -> None:
        for fd in self._fds:
            os.close(fd)
        self._fds.clear()

    def __enter__(self) -> "PhysicalKeyboard":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
