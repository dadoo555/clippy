"""Clippy: a voice assistant for the Arduino UNO Q.

Phase 1 provides a text-only conversation loop with the Gemini API where the model
also picks a face expression each turn. Voice (Whisper/Piper), the MAX7219 LED-matrix
face on the MCU, and the state machine plug in later without rewriting the brain.
"""

from __future__ import annotations

__version__ = "0.1.0"
