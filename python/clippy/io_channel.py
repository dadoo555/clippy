"""User I/O channel: how Clippy reads the user and speaks back.

Phase 1 is terminal text. Phase 2 adds `VoiceIOChannel` (faster-whisper for input,
Piper for output) implementing the same Protocol, so nothing else changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IOChannel(Protocol):
    def get_user_input(self) -> str | None: ...  # None means "end the session" (EOF)

    def speak(self, text: str) -> None: ...


class TextIOChannel:
    """Phase 1: input() for input, print() for output."""

    def get_user_input(self) -> str | None:
        try:
            return input("você > ")
        except EOFError:
            return None

    def speak(self, text: str) -> None:
        print(f"clippy > {text}")
