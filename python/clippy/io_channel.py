"""User I/O channel for the text `chat` mode: how Clippy reads the user and speaks back.

Voice now lives in the real-time Live API path (`clippy/live.py`), separate from this text loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AudioInput:
    """A recorded user utterance sent straight to Gemini (no local transcription)."""

    data: bytes                     # WAV bytes (PCM16, mono)
    mime_type: str = "audio/wav"


# A user turn is either typed/transcribed text or raw audio for Gemini to understand.
UserInput = "str | AudioInput"


@runtime_checkable
class IOChannel(Protocol):
    def get_user_input(self) -> "str | AudioInput | None": ...  # None ends the session (EOF)

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
