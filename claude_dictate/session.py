import re
import subprocess
from dataclasses import dataclass

SOCKET = "claude-dictate"
TARGET = "claude-dictate:0"

CTRL_SHIFT_SPACE = b"\x1b[32;6u"
END_KEY = b"\x1b[F"
CTRL_U = b"\x15"

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;:?]*[A-Za-z]")


@dataclass(frozen=True)
class Snapshot:
    styled: str
    cursor_x: int
    cursor_y: int
    width: int
    height: int

    @property
    def text(self) -> str:
        return ANSI_ESCAPE.sub("", self.styled)


def _tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", "-L", SOCKET, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def is_running() -> bool:
    try:
        _tmux("has-session", "-t", TARGET)
        return True
    except subprocess.CalledProcessError:
        return False


def send_bytes(data: bytes) -> None:
    _tmux("send-keys", "-t", TARGET, "-H", *(f"{b:02x}" for b in data))


def push_to_talk_tick() -> None:
    send_bytes(CTRL_SHIFT_SPACE)


def kill_visual_line() -> None:
    send_bytes(END_KEY + CTRL_U)


def snapshot() -> Snapshot:
    styled = _tmux("capture-pane", "-t", TARGET, "-p", "-e")
    x, y, w, h = _tmux(
        "display", "-p", "-t", TARGET,
        "#{cursor_x} #{cursor_y} #{pane_width} #{pane_height}",
    ).split()
    return Snapshot(styled, int(x), int(y), int(w), int(h))
