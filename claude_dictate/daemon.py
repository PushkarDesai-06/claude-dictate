import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from claude_dictate import session
from claude_dictate.dictator import Dictator, UnsafeToType
from claude_dictate.ipc import COMMANDS, SOCKET_PATH, send_command
from claude_dictate.keyboard import PhysicalKeyboard
from claude_dictate.typers import YdotoolTyper

LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "claude-dictate-start"
SESSION_BOOT_TIMEOUT = 20.0

log = logging.getLogger("claude_dictate")


def notify(message: str) -> None:
    try:
        subprocess.run(
            ["notify-send", "--app-name=claude-dictate", "claude-dictate", message],
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.warning("could not show notification: %s", message)


def copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=2,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        log.warning("could not copy the transcript to the clipboard")
        return False


def report_error(error: Exception) -> None:
    if not isinstance(error, UnsafeToType):
        notify(str(error))
    elif copy_to_clipboard(error.transcript):
        notify(f"{error} The transcript is on your clipboard.")
    else:
        notify(f"{error} Transcript: {error.transcript}")


def ensure_session() -> None:
    if session.is_running():
        return
    log.info("starting dictation session")
    subprocess.run([str(LAUNCHER), "--detached"], check=True)
    deadline = time.monotonic() + SESSION_BOOT_TIMEOUT
    while time.monotonic() < deadline:
        if "❯" in session.snapshot().text:
            return
        time.sleep(0.5)
    raise RuntimeError("dictation session did not finish booting")


def already_serving(socket_path: Path) -> bool:
    try:
        send_command("status", socket_path, timeout=0.5)
        return True
    except OSError:
        return False


def bind_socket(socket_path: Path) -> socket.socket:
    if socket_path.exists():
        if already_serving(socket_path):
            sys.exit(f"claude-dictated is already running on {socket_path}")
        socket_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o177)
    try:
        server.bind(str(socket_path))
    finally:
        os.umask(old_umask)
    server.listen()
    return server


def handle(connection: socket.socket, dictator: Dictator) -> None:
    with connection:
        command = connection.makefile().readline().strip()
        if command in COMMANDS:
            reply = getattr(dictator, command)()
        else:
            reply = f"error: unknown command {command!r}"
        if command != "status":
            log.info("%s -> %s", command, reply)
        connection.sendall(reply.encode() + b"\n")


def serve(socket_path: Path = SOCKET_PATH) -> None:
    dictator = Dictator(YdotoolTyper(), PhysicalKeyboard, on_error=report_error)
    server = bind_socket(socket_path)
    log.info("listening on %s", socket_path)
    try:
        while True:
            connection, _ = server.accept()
            try:
                handle(connection, dictator)
            except OSError:
                log.exception("client connection failed")
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)


def exit_cleanly(*_signal_args) -> None:
    sys.exit(0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, exit_cleanly)
    try:
        ensure_session()
    except (subprocess.CalledProcessError, RuntimeError) as error:
        notify(f"could not start dictation session: {error}")
        raise
    try:
        serve()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
