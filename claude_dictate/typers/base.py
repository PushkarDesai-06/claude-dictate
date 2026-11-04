from abc import ABC, abstractmethod


class TextTyper(ABC):
    """Delivers text into whichever application currently has keyboard focus."""

    @abstractmethod
    def type_text(self, text: str) -> None: ...
