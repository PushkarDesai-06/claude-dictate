import time

from claude_dictate import session
from claude_dictate.session import ANSI_ESCAPE, Snapshot

RULE_CHAR = "─"
PROMPT_PREFIX = "❯ "
CONTINUATION_PREFIX = "  "
DIM = "\x1b[2m"
LEVEL_METER_GLYPHS = "▁▂▃▄▅▆▇█"


class InputBoxNotFound(RuntimeError):
    pass


def _input_box_rows(styled: str) -> list[str]:
    rows = styled.split("\n")
    rule_indices = [
        i for i, row in enumerate(rows)
        if ANSI_ESCAPE.sub("", row).startswith(RULE_CHAR * 3)
    ]
    if len(rule_indices) < 2:
        raise InputBoxNotFound("could not find the two rules around the input box")
    top, bottom = rule_indices[-2], rule_indices[-1]
    box = rows[top + 1:bottom]
    if not box or PROMPT_PREFIX not in box[0]:
        raise InputBoxNotFound("input box does not start with the prompt marker")
    return box


def _shows_placeholder(first_styled_row: str) -> bool:
    after_prompt = first_styled_row.split(PROMPT_PREFIX, 1)[1]
    return after_prompt.startswith(DIM)


def _strip_prefix(row: str, prefix: str) -> str:
    return row[len(prefix):] if row.startswith(prefix) else row.lstrip()


def parse_input_box(styled: str) -> str:
    box = _input_box_rows(styled)
    if _shows_placeholder(box[0]):
        return ""

    plain = [ANSI_ESCAPE.sub("", row).rstrip() for row in box]
    plain[0] = plain[0].split(PROMPT_PREFIX, 1)[1]
    parts = [plain[0]] + [_strip_prefix(row, CONTINUATION_PREFIX) for row in plain[1:]]
    joined = " ".join(part for part in parts if part)
    return joined.rstrip(LEVEL_METER_GLYPHS).rstrip()


def read_input(snap: Snapshot | None = None) -> str:
    return parse_input_box((snap or session.snapshot()).styled)


def get_transcript() -> str:
    return read_input()


def clear_input(max_attempts: int = 20, settle_seconds: float = 0.08) -> None:
    for _ in range(max_attempts):
        if read_input() == "":
            return
        session.kill_visual_line()
        time.sleep(settle_seconds)
    if read_input() != "":
        raise RuntimeError("input box did not clear")
