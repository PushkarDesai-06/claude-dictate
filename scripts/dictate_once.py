"""Run one dictation: speak, then press Enter (or use --hold) and print the transcript."""

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_dictate import dictation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, help="release automatically after N seconds")
    parser.add_argument("--quiet", type=float, default=dictation.QUIET_SECONDS)
    parser.add_argument("--tail", type=float, default=dictation.RELEASE_TAIL_SECONDS)
    args = parser.parse_args()

    release = threading.Event()
    released_at = None

    def release_now() -> None:
        nonlocal released_at
        released_at = time.monotonic()
        release.set()

    if args.hold:
        threading.Timer(args.hold, release_now).start()
        print(f">>> SPEAK NOW (releasing in {args.hold:g}s) <<<", flush=True)
    else:
        def wait_for_enter() -> None:
            input(">>> SPEAK NOW, press Enter when done <<<\n")
            release_now()
        threading.Thread(target=wait_for_enter, daemon=True).start()

    text = dictation.dictate(release, quiet_seconds=args.quiet, release_tail_seconds=args.tail)
    latency = time.monotonic() - released_at
    print(f"\nTranscript ({len(text)} chars, {latency:.2f}s after release):\n{text!r}")


if __name__ == "__main__":
    main()
