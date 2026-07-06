"""Speech-to-text with faster-whisper (CTranslate2 backend, no PyTorch).

Torch-free on purpose: the sibling project documented PyTorch SIGILL crashes on the UNO Q's
ARM CPU. faster-whisper runs on CTranslate2 + onnxruntime, which install cleanly here.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class WhisperSTT:
    def __init__(self, cfg: dict[str, Any]) -> None:
        stt = cfg.get("voice", {}).get("stt", {})
        self._language = stt.get("language", "pt")
        model_name = stt.get("model", "base")
        compute_type = stt.get("compute_type", "int8")

        # Imported lazily so text-only mode never pays for it.
        from faster_whisper import WhisperModel

        print(f"Carregando modelo Whisper '{model_name}' (primeira vez baixa da internet)...")
        self._model = WhisperModel(model_name, device="cpu", compute_type=compute_type)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe a mono float32 array (16 kHz). Returns stripped text ('' if nothing)."""
        # beam_size=1 (greedy) is much faster than the default beam search and fine for short
        # conversational clips. vad_filter (Silero onnx) trims silence, so Whisper sees less audio.
        segments, _ = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
