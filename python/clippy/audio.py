"""Microphone capture (press-to-talk with silence auto-stop) and playback via sounddevice.

Push-to-talk removes the unreliable part of energy VAD (guessing when speech *starts*): the caller
triggers recording, and we only use the energy threshold to detect when the user *stops* talking.
"""

from __future__ import annotations

import io
import sys
import threading
import wave
from typing import Any

import numpy as np
import sounddevice as sd

_FRAME_MS = 30  # analysis frame size for the energy detector


def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(frame)) + 1e-12))


def float_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode a mono float32 array (-1..1) as PCM16 WAV bytes (for sending audio to Gemini)."""
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16.tobytes())
    return buf.getvalue()


class AudioIO:
    def __init__(self, cfg: dict[str, Any]) -> None:
        voice = cfg.get("voice", {})
        self.sample_rate = int(voice.get("sample_rate", 16000))
        self._input_device = voice.get("input_device")     # None = system default
        self._output_device = voice.get("output_device")
        self._silence_ms = int(voice.get("silence_ms", 700))
        self._max_utterance_s = float(voice.get("max_utterance_s", 12))
        self._no_speech_giveup_s = float(voice.get("no_speech_giveup_s", 4))
        self.threshold = voice.get("silence_threshold")     # None = auto-calibrate

    def calibrate(self) -> None:
        """Measure ambient noise for ~0.3 s and set the stop threshold just above it."""
        if self.threshold is not None:
            return
        frame_len = int(self.sample_rate * _FRAME_MS / 1000)
        levels = []
        with sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32", device=self._input_device
        ) as stream:
            for _ in range(int(300 / _FRAME_MS)):
                data, _ov = stream.read(frame_len)
                levels.append(_rms(data[:, 0]))
        noise = float(np.median(levels)) if levels else 0.0
        # Biased low: this only decides when the user has *stopped*, so a low value is safe.
        self.threshold = max(noise * 2.5, 0.008)

    def record_until_enter(self) -> np.ndarray | None:
        """Record on a background thread until the user presses ENTER. Returns float32 mono, or None.

        The user controls exactly when the utterance ends — no energy-VAD guessing, so it never
        cuts a sentence short.
        """
        sr = self.sample_rate
        frame_len = int(sr * _FRAME_MS / 1000)
        frames: list[np.ndarray] = []
        stop = threading.Event()

        def worker() -> None:
            try:
                with sd.InputStream(
                    samplerate=sr, channels=1, dtype="float32", device=self._input_device
                ) as stream:
                    while not stop.is_set():
                        data, _ov = stream.read(frame_len)
                        frames.append(data[:, 0].copy())
            except Exception as exc:
                print(f"[erro áudio] {type(exc).__name__}: {exc}", file=sys.stderr)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            input()  # block until ENTER
        except (EOFError, KeyboardInterrupt):
            pass
        stop.set()
        thread.join(timeout=1.0)

        if not frames:
            return None
        audio = np.concatenate(frames)
        if len(audio) < 0.3 * sr:  # too short to be a real utterance
            return None
        return audio

    def play(self, samples: np.ndarray, sample_rate: int) -> None:
        sd.play(samples, sample_rate, device=self._output_device)
        sd.wait()
