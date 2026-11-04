"""Hold push-to-talk for a fixed time and record every distinct frame of the pane."""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_dictate import session, transcript

TICK_SECONDS = 0.03
SAMPLE_SECONDS = 0.1


def countdown(seconds: int) -> None:
    for remaining in range(seconds, 0, -1):
        print(f"  starting in {remaining}...", flush=True)
        time.sleep(1)


def record(hold: float, settle: float, out: Path) -> None:
    frames = []
    last_text = None
    start = time.monotonic()
    next_tick = next_sample = start

    def sample(phase: str) -> None:
        nonlocal last_text
        snap = session.snapshot()
        if snap.text != last_text:
            frames.append({
                "t": round(time.monotonic() - start, 3),
                "phase": phase,
                "transcript": transcript.read_input(snap),
                **asdict(snap),
            })
            last_text = snap.text

    print(">>> SPEAK NOW <<<", flush=True)
    while (now := time.monotonic()) - start < hold:
        if now >= next_tick:
            session.push_to_talk_tick()
            next_tick += TICK_SECONDS
        if now >= next_sample:
            sample("hold")
            next_sample += SAMPLE_SECONDS
        time.sleep(0.005)
    print(">>> released, waiting for transcript <<<", flush=True)

    released = time.monotonic()
    while time.monotonic() - released < settle:
        sample("settle")
        time.sleep(SAMPLE_SECONDS)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(f) for f in frames) + "\n")
    print(f"Recorded {len(frames)} distinct frames to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", type=float, default=10.0)
    parser.add_argument("--settle", type=float, default=6.0)
    parser.add_argument("--out", type=Path, default=Path("probe-output/frames.jsonl"))
    args = parser.parse_args()

    if not session.is_running():
        sys.exit("claude-dictate session is not running. Start it with claude-dictate-start.")

    transcript.clear_input()
    countdown(3)
    record(args.hold, args.settle, args.out)


if __name__ == "__main__":
    main()
