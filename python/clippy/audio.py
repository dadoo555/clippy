"""Microphone capture (press-to-talk with silence auto-stop) and playback via sounddevice.

Push-to-talk removes the unreliable part of energy VAD (guessing when speech *starts*): the caller
triggers recording, and we only use the energy threshold to detect when the user *stops* talking.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import sounddevice as sd

_FRAME_MS = 30  # analysis frame size for the energy detector


def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(frame)) + 1e-12))


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

    def record_after_trigger(self) -> np.ndarray | None:
        """Record from now until trailing silence (or a cap). Returns float32 mono, or None."""
        sr = self.sample_rate
        frame_len = int(sr * _FRAME_MS / 1000)
        silence_needed = max(1, self._silence_ms // _FRAME_MS)
        max_frames = int(self._max_utterance_s * 1000 / _FRAME_MS)
        giveup_frames = int(self._no_speech_giveup_s * 1000 / _FRAME_MS)
        threshold = self.threshold if self.threshold is not None else 0.008

        collected: list[np.ndarray] = []
        silence_count = 0
        heard_speech = False

        with sd.InputStream(
            samplerate=sr, channels=1, dtype="float32", device=self._input_device
        ) as stream:
            for i in range(max_frames):
                data, _ov = stream.read(frame_len)
                frame = data[:, 0].copy()
                collected.append(frame)

                if _rms(frame) > threshold:
                    heard_speech = True
                    silence_count = 0
                else:
                    silence_count += 1

                if heard_speech and silence_count >= silence_needed:
                    break
                if not heard_speech and i >= giveup_frames:
                    return None  # nobody spoke

        if not heard_speech or not collected:
            return None
        return np.concatenate(collected)

    def play(self, samples: np.ndarray, sample_rate: int) -> None:
        sd.play(samples, sample_rate, device=self._output_device)
        sd.wait()
