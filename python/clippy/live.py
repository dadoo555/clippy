"""Real-time voice conversation with the Gemini Live API, gated by a wake word.

State machine:
  DORMINDO  -> local Vosk listens for "clippy" (no API cost)
  ACORDADO  -> Gemini Live session (audio in/out, search, face via set_face)
  after `inactivity_timeout_s` with no speech -> back to DORMINDO

Adapted from the Live API cookbook: no camera/screen, sounddevice instead of pyaudio, a Clippy
persona + PT-BR voice. Mic streams 16 kHz PCM; Gemini's voice comes back at 24 kHz.
"""

from __future__ import annotations

import array
import asyncio
import os
import sys
import time
from typing import Any

import sounddevice as sd

from .env import load_env
from .expressions import Expression
from .face import FaceDisplay, TextFaceDisplay
from .settings import load_config

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK = 1024


def _build_config(types: Any, cfg: dict[str, Any]) -> Any:
    gemini_cfg = cfg.get("gemini", {})
    live_cfg = cfg.get("live", {})
    persona = gemini_cfg.get("persona", "")

    tools = []
    if gemini_cfg.get("web_search", True):
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    system = persona
    if live_cfg.get("face_tool", True):
        names = ", ".join(e.value for e in Expression)
        system = persona + (
            f"\n\nChame a função set_face sempre que seu humor mudar, escolhendo uma destas "
            f"expressões: {names}."
        )
        set_face = types.FunctionDeclaration(
            name="set_face",
            description="Mostra a expressão de rosto do Clippy na matriz de LED.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "expression": types.Schema(
                        type=types.Type.STRING, enum=[e.value for e in Expression]
                    )
                },
                required=["expression"],
            ),
        )
        tools.append(types.Tool(function_declarations=[set_face]))

    # Default VAD (snappy). Half-duplex already stops echo from interrupting Gemini, so we don't
    # slow down turn detection with low sensitivities.
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=live_cfg.get("voice", "Leda")
                )
            )
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=tools,
    )


class LiveClippy:
    def __init__(self, cfg: dict[str, Any], face: FaceDisplay) -> None:
        self._cfg = cfg
        self._face = face
        live_cfg = cfg.get("live", {})
        self._input_device = live_cfg.get("input_device")
        self._output_device = live_cfg.get("output_device")
        self._timeout = float(live_cfg.get("inactivity_timeout_s", 10))
        # Mean sample amplitude above this counts as "you are speaking" (keeps it awake).
        self._speech_level = float(live_cfg.get("speech_level", 300))
        # Half-duplex: mute the mic while Gemini talks so its own voice (echo) does not
        # interrupt it. Set false for barge-in (interrupt by talking over it).
        self._half_duplex = bool(live_cfg.get("half_duplex", True))
        self._session: Any = None
        self._audio_in_queue: asyncio.Queue[bytes] | None = None
        self._out_queue: asyncio.Queue[bytes] | None = None
        self._stop: asyncio.Event | None = None
        self._last_activity = 0.0
        self._last_play = 0.0
        self._reason = ""

    def _gemini_speaking(self) -> bool:
        if self._audio_in_queue is not None and not self._audio_in_queue.empty():
            return True
        return (time.monotonic() - self._last_play) < 0.4  # brief grace after the last chunk

    @staticmethod
    def _flush_input(stream: Any) -> None:
        """Drop already-buffered audio (wake-word residual) so it is not sent as the first turn.

        Only clears what is already buffered — instant, no added delay before detection starts.
        """
        try:
            while stream.read_available > 0:
                stream.read(stream.read_available)
        except Exception:
            pass

    async def _listen_audio(self) -> None:
        stream = sd.RawInputStream(
            samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16",
            blocksize=CHUNK, device=self._input_device,
        )
        stream.start()
        await asyncio.to_thread(self._flush_input, stream)
        try:
            while True:
                data, _ov = await asyncio.to_thread(stream.read, CHUNK)
                chunk = bytes(data)
                # Half-duplex: while Gemini is talking, drop the mic so its echoed voice is not
                # sent back and mistaken for you interrupting (which cut off the first reply).
                if self._half_duplex and self._gemini_speaking():
                    continue
                # Keep awake while YOU are speaking: server messages only arrive when Gemini
                # speaks/transcribes, so without this the timeout could fire mid-utterance.
                samples = array.array("h")
                samples.frombytes(chunk)
                if samples and (sum(abs(s) for s in samples) / len(samples)) > self._speech_level:
                    self._last_activity = time.monotonic()
                if self._out_queue is not None:
                    await self._out_queue.put(chunk)
        finally:
            stream.stop()
            stream.close()

    async def _send_realtime(self) -> None:
        from google.genai import types

        while True:
            chunk = await self._out_queue.get()  # type: ignore[union-attr]
            await self._session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}")
            )

    async def _receive(self) -> None:
        while True:
            turn = self._session.receive()
            async for response in turn:
                if response.data:
                    self._last_activity = time.monotonic()
                    self._audio_in_queue.put_nowait(response.data)  # type: ignore[union-attr]
                if response.tool_call:
                    self._last_activity = time.monotonic()
                    await self._handle_tool_call(response.tool_call)
                sc = response.server_content
                if sc:
                    if sc.output_transcription and sc.output_transcription.text:
                        self._last_activity = time.monotonic()
                        print(sc.output_transcription.text, end="", flush=True)
                    if sc.input_transcription and sc.input_transcription.text:
                        self._last_activity = time.monotonic()
                        print(f"\nvocê: {sc.input_transcription.text}")
                    if sc.interrupted:
                        self._drain_playback()
            self._drain_playback()

    def _drain_playback(self) -> None:
        if self._audio_in_queue is None:
            return
        while not self._audio_in_queue.empty():
            self._audio_in_queue.get_nowait()

    async def _handle_tool_call(self, tool_call: Any) -> None:
        from google.genai import types

        responses = []
        for fc in tool_call.function_calls or []:
            if fc.name == "set_face":
                name = (fc.args or {}).get("expression", "neutro")
                try:
                    self._face.set_expression(Expression(name))
                except ValueError:
                    self._face.set_expression(Expression.neutro)
            responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"ok": True}))
        if responses:
            await self._session.send_tool_response(function_responses=responses)

    async def _play_audio(self) -> None:
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16",
            device=self._output_device,
        )
        stream.start()
        try:
            while True:
                chunk = await self._audio_in_queue.get()  # type: ignore[union-attr]
                # Playing Gemini's voice counts as activity: generation (response.data) can finish
                # long before playback does, so reset the timer while the audio is still being heard.
                self._last_activity = self._last_play = time.monotonic()
                await asyncio.to_thread(stream.write, chunk)
                self._last_activity = self._last_play = time.monotonic()
        finally:
            stream.stop()
            stream.close()

    async def _monitor(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            if time.monotonic() - self._last_activity > self._timeout:
                self._reason = "timeout"
                if self._stop is not None:
                    self._stop.set()
                return

    async def _guard(self, coro_fn: Any) -> None:
        try:
            await coro_fn()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"\n[erro Live] {type(exc).__name__}: {exc}", file=sys.stderr)
            self._reason = self._reason or "erro"
            if self._stop is not None:
                self._stop.set()

    async def run_once(self) -> str:
        """One Live session: converse until inactivity timeout or error. Returns the reason."""
        from google import genai
        from google.genai import types

        live_cfg = self._cfg.get("live", {})
        model = live_cfg.get("model", "gemini-3.1-flash-live-preview")
        api_version = live_cfg.get("api_version", "v1beta")
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"], http_options={"api_version": api_version}
        )
        config = _build_config(types, self._cfg)

        self._reason = ""
        try:
            async with client.aio.live.connect(model=model, config=config) as session:
                self._session = session
                self._audio_in_queue = asyncio.Queue()
                self._out_queue = asyncio.Queue(maxsize=20)
                self._stop = asyncio.Event()
                self._last_activity = time.monotonic()
                tasks = [
                    asyncio.create_task(self._guard(c))
                    for c in (self._listen_audio, self._send_realtime, self._receive,
                              self._play_audio, self._monitor)
                ]
                try:
                    await self._stop.wait()
                finally:
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            print(f"\n[erro Live] {type(exc).__name__}: {exc}", file=sys.stderr)
            if isinstance(exc, BaseExceptionGroup):
                for sub in exc.exceptions:
                    print(f"  - {type(sub).__name__}: {sub}", file=sys.stderr)
            return "erro"
        return self._reason or "fim"


def run_live(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg or load_config(None)
    load_env()
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY não definida (veja o README / python/.env).", file=sys.stderr)
        return 1

    face: FaceDisplay = TextFaceDisplay()  # MatrixFaceDisplay on the board (MAX7219 via Bridge)

    # Optional wake word: sleeps until "clippy" is heard, so the API is only used while active.
    wake = None
    wake_cfg = cfg.get("wake", {})
    if wake_cfg.get("enabled", True) and wake_cfg.get("model_path"):
        try:
            from .wake import WakeWord

            wake = WakeWord(cfg)
        except Exception as exc:
            print(f"[aviso] wake word desligado: {exc}\n", file=sys.stderr)

    clippy = LiveClippy(cfg, face)
    try:
        while True:
            if wake is not None:
                face.set_expression(Expression.dormindo)
                print('\n💤 dormindo — diga "clippy" para acordar (Ctrl-C para sair)')
                if not wake.wait():
                    break
                print("👂 acordei! Pode falar.")

            face.set_expression(Expression.neutro)
            reason = asyncio.run(clippy.run_once())

            if wake is None:
                break  # no wake gate: run one session then exit
            if reason == "timeout":
                print("\n💤 (10s sem fala) voltando a dormir...")
            elif reason == "erro":
                break  # don't spin on a persistent connection error
    except KeyboardInterrupt:
        pass
    print("\nAté logo! 👋")
    return 0
