import os
import socket
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "claude-dictate.sock"
COMMANDS = ("press", "release", "status")


def send_command(command: str, socket_path: Path = SOCKET_PATH, timeout: float = 2.0) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(command.encode() + b"\n")
        return client.makefile().readline().strip()
