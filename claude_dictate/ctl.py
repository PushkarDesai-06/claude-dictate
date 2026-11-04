import sys

from claude_dictate.ipc import COMMANDS, SOCKET_PATH, send_command


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: claude-dictate-ctl {{{'|'.join(COMMANDS)}}}")
    try:
        print(send_command(sys.argv[1]))
    except OSError as error:
        sys.exit(f"claude-dictated is not reachable on {SOCKET_PATH}: {error}")


if __name__ == "__main__":
    main()
