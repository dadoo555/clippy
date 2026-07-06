"""VoiceIOChannel: microphone in (VAD + Whisper), speaker out (TTS).

Implements the same IOChannel Protocol as TextIOChannel, so the brain, session and face are
unchanged — only the I/O backend swaps. The transcription is printed too (useful on screen and
for debugging), as the brief noted.
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any

from .audio import AudioIO
from .stt import WhisperSTT
from .tts import PLAYBACK_SR, decode_audio, make_tts


class VoiceIOChannel:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self._audio = AudioIO(cfg)
        self._stt = WhisperSTT(cfg)
        self._tts = make_tts(cfg)
        print("Calibrando o microfone (fique em silêncio um instante)...")
        self._audio.calibrate()
        print(f"Pronto. (limiar de silêncio: {self._audio.threshold:.4f})")

    def get_user_input(self) -> str | None:
        # Press-to-talk: ENTER starts recording; typing text instead is a fallback (and lets
        # 'sair' work even if the mic misbehaves).
        try:
            typed = input("\n⏎ ENTER e fale  (ou digite algo / 'sair'): ")
        except EOFError:
            return None
        if typed.strip():
            return typed.strip()

        print("🔴 gravando... (fale; a pausa encerra)")
        try:
            audio = self._audio.record_after_trigger()
        except KeyboardInterrupt:
            return None
        if audio is None:
            print("(não ouvi nada — tenta de novo)")
            return ""
        print("⏳ transcrevendo...")
        text = self._stt.transcribe(audio, self._audio.sample_rate)
        print(f"você (voz) > {text}")
        return text

    def speak(self, text: str) -> None:
        print(f"clippy > {text}")
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            self._tts.synth_to_file(text, tmp_path)
            samples = decode_audio(tmp_path, PLAYBACK_SR)
            if len(samples):
                self._audio.play(samples, PLAYBACK_SR)
        except Exception as exc:
            # Never let a TTS/network hiccup crash the conversation; the text is already printed.
            print(f"[erro TTS] {type(exc).__name__}: {exc}", file=sys.stderr)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
