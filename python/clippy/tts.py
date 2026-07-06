"""Text-to-speech backends and audio-file decoding.

`EdgeTts` (default) uses Microsoft's online voices — pure Python, great PT-BR, installs
everywhere (good for Windows dev). `PiperTts` is the offline path for the board. Both produce
an audio file that `decode_audio` turns into a float32 array for sounddevice playback.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np

# Everything is resampled to this rate for playback (edge=24k, piper=22.05k -> unified).
PLAYBACK_SR = 24000


def decode_audio(path: str, target_sr: int = PLAYBACK_SR) -> np.ndarray:
    """Decode any audio file (mp3/wav/...) to mono float32 at target_sr using PyAV."""
    import av
    from av.audio.resampler import AudioResampler

    resampler = AudioResampler(format="s16", layout="mono", rate=target_sr)
    chunks: list[np.ndarray] = []
    with av.open(path) as container:
        for frame in container.decode(audio=0):
            for rframe in resampler.resample(frame):
                chunks.append(rframe.to_ndarray().reshape(-1))
        # Flush any buffered samples.
        for rframe in resampler.resample(None):
            chunks.append(rframe.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


@runtime_checkable
class Tts(Protocol):
    def synth_to_file(self, text: str, path: str) -> None: ...


class EdgeTts:
    """Online TTS via edge-tts. Needs internet (so does Gemini, so no new requirement in practice)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._voice = cfg.get("voice", {}).get("tts", {}).get("edge_voice", "pt-BR-AntonioNeural")

    def synth_to_file(self, text: str, path: str) -> None:
        import asyncio

        import edge_tts

        async def _run() -> None:
            await edge_tts.Communicate(text, self._voice).save(path)

        asyncio.run(_run())


class PiperTts:
    """Offline TTS via Piper (for the UNO Q). Install separately: pip install piper-tts.

    Set voice.tts.piper_model in config to a downloaded .onnx voice. Untested on Windows dev.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        model_path = cfg.get("voice", {}).get("tts", {}).get("piper_model", "")
        if not model_path:
            raise RuntimeError("voice.tts.piper_model não configurado (caminho do .onnx do Piper).")
        from piper import PiperVoice

        self._voice = PiperVoice.load(model_path)

    def synth_to_file(self, text: str, path: str) -> None:
        import wave

        with wave.open(path, "wb") as wav:
            self._voice.synthesize(text, wav)


def make_tts(cfg: dict[str, Any]) -> Tts:
    engine = cfg.get("voice", {}).get("tts", {}).get("engine", "edge").lower()
    if engine == "piper":
        return PiperTts(cfg)
    return EdgeTts(cfg)
