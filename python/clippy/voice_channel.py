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

from .audio import AudioIO, float_to_wav_bytes
from .io_channel import AudioInput
from .tts import PLAYBACK_SR, decode_audio, make_tts


class VoiceIOChannel:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self._audio = AudioIO(cfg)
        # stt_engine: 'gemini' sends audio straight to the model (no Whisper); 'whisper' is local.
        self._engine = cfg.get("voice", {}).get("stt_engine", "gemini").lower()
        self._stt = None
        if self._engine == "whisper":
            from .stt import WhisperSTT

            self._stt = WhisperSTT(cfg)
        self._tts = make_tts(cfg)
        print(f"Voz pronta (motor: {self._engine}).")

    def get_user_input(self) -> "str | AudioInput | None":
        # Press ENTER to start, speak, press ENTER again to stop. Typing text instead is a
        # fallback (and lets 'sair' work even if the mic misbehaves).
        try:
            typed = input("\n⏎ ENTER e fale (ENTER de novo p/ parar)  ou digite algo / 'sair': ")
        except EOFError:
            return None
        if typed.strip():
            return typed.strip()

        print("🔴 gravando... (aperte ENTER quando terminar de falar)")
        try:
            audio = self._audio.record_until_enter()
        except KeyboardInterrupt:
            return None
        if audio is None:
            print("(não ouvi nada — tenta de novo)")
            return ""

        if self._engine == "whisper":
            print("⏳ transcrevendo...")
            text = self._stt.transcribe(audio, self._audio.sample_rate)
            print(f"você (voz) > {text}")
            return text

        # gemini engine: hand the raw audio to the brain (transcription comes back in reply.heard).
        print("⏳ enviando áudio ao Gemini...")
        return AudioInput(data=float_to_wav_bytes(audio, self._audio.sample_rate))

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
