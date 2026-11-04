import subprocess
import unicodedata
from dataclasses import dataclass

from claude_dictate.typers.base import TextTyper

PUNCTUATION_TO_ASCII = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    "…": "...",
    " ": " ", " ": " ", " ": " ",
})


def to_typeable_ascii(text: str) -> str:
    text = text.translate(PUNCTUATION_TO_ASCII)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if ch.isascii() and (ch.isprintable() or ch in "\n\t"))


@dataclass(frozen=True)
class YdotoolTyper(TextTyper):
    """Types via ydotool's virtual keyboard, which can only press keys on the layout, so text is reduced to ASCII."""

    key_hold_ms: int = 2
    key_delay_ms: int = 2

    def type_text(self, text: str) -> None:
        typeable = to_typeable_ascii(text)
        if not typeable:
            return
        subprocess.run(
            [
                "ydotool", "type",
                "--key-hold", str(self.key_hold_ms),
                "--key-delay", str(self.key_delay_ms),
                "--", typeable,
            ],
            check=True,
            capture_output=True,
        )
