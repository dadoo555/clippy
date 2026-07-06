"""Local wake-word listening with Vosk (offline, no account/key, works on Windows and the board).

Runs a small speech recognizer on the mic and returns when a wake phrase ("clippy" and common
mishearings) is heard. Only active while Clippy is asleep, so it does not cost any API.
"""

from __future__ import annotations

import json
import os
from typing import Any

import sounddevice as sd

_SAMPLE_RATE = 16000
_FRAME = int(_SAMPLE_RATE * 0.2)  # 200 ms reads


def _looks_like_model(d: str) -> bool:
    """A Vosk model folder has these subfolders."""
    return os.path.isdir(os.path.join(d, "conf")) and (
        os.path.isdir(os.path.join(d, "am")) or os.path.isdir(os.path.join(d, "graph"))
    )


def _resolve_model_dir(path: str) -> str | None:
    """Return the real model dir, descending one level if the zip nested it (common case)."""
    if _looks_like_model(path):
        return path
    try:
        subdirs = [os.path.join(path, d) for d in os.listdir(path)]
    except OSError:
        return None
    models = [d for d in subdirs if os.path.isdir(d) and _looks_like_model(d)]
    return models[0] if len(models) == 1 else None


class WakeWord:
    def __init__(self, cfg: dict[str, Any]) -> None:
        wake_cfg = cfg.get("wake", {})
        self._device = cfg.get("live", {}).get("input_device")
        self._phrases = [p.lower() for p in wake_cfg.get("phrases", ["clip", "clipe", "clipi", "clippy", "clique"])]

        model_path = wake_cfg.get("model_path", "")
        if not model_path or not os.path.isdir(model_path):
            raise RuntimeError(
                f"wake.model_path ('{model_path}') não é uma pasta. Baixe um modelo pequeno em "
                "https://alphacephei.com/vosk/models (ex.: vosk-model-small-pt-0.3), descompacte, "
                "e coloque o caminho da PASTA em `wake.model_path` no config.yaml."
            )

        resolved = _resolve_model_dir(model_path)
        if resolved is None:
            try:
                contents = ", ".join(sorted(os.listdir(model_path))) or "(vazia)"
            except OSError:
                contents = "(ilegível)"
            raise RuntimeError(
                f"'{model_path}' não parece um modelo Vosk (falta 'conf' + 'am'/'graph'). "
                f"Conteúdo: {contents}. Se essa pasta CONTÉM a pasta do modelo, aponte para a de "
                "dentro."
            )

        import vosk

        vosk.SetLogLevel(-1)  # silence Kaldi logs
        self._vosk = vosk
        self._model = vosk.Model(resolved)

    def _matches(self, text: str) -> bool:
        text = text.lower()
        return any(p in text for p in self._phrases)

    def wait(self) -> bool:
        """Block until a wake phrase is heard. Returns True; False if interrupted (Ctrl-C)."""
        rec = self._vosk.KaldiRecognizer(self._model, _SAMPLE_RATE)
        try:
            with sd.RawInputStream(
                samplerate=_SAMPLE_RATE, channels=1, dtype="int16", blocksize=_FRAME,
                device=self._device,
            ) as stream:
                while True:
                    data, _ov = stream.read(_FRAME)
                    chunk = bytes(data)
                    if rec.AcceptWaveform(chunk):
                        text = json.loads(rec.Result()).get("text", "")
                    else:
                        text = json.loads(rec.PartialResult()).get("partial", "")
                    if text and self._matches(text):
                        return True
        except KeyboardInterrupt:
            return False
