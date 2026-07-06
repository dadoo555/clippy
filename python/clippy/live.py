"""Real-time voice conversation with the Gemini Live API (audio in, audio out).

Adapted from the Live API cookbook example: no camera/screen, sounddevice instead of pyaudio
(pyaudio needs a C compiler on this Python), a Clippy persona + PT-BR voice, Google Search
grounding, and the face chosen by Gemini through a `set_face` function call.

Mic streams at 16 kHz PCM; Gemini's voice comes back at 24 kHz PCM and is played live.
Press Ctrl-C to stop.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import sounddevice as sd

from .env import load_env
from .expressions import Expression
from .face import FaceDisplay, TextFaceDisplay
from .settings import load_config

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK = 1024  # frames per mic read


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
        system = (
            persona
            + f"\n\nChame a função set_face sempre que seu humor mudar, escolhendo uma destas "
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
        self._session: Any = None
        self._audio_in_queue: asyncio.Queue[bytes] | None = None
        self._out_queue: asyncio.Queue[bytes] | None = None

    async def _listen_audio(self) -> None:
        stream = sd.RawInputStream(
            samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=CHUNK
        )
        stream.start()
        try:
            while True:
                data, _overflowed = await asyncio.to_thread(stream.read, CHUNK)
                if self._out_queue is not None:
                    await self._out_queue.put(bytes(data))
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
                    self._audio_in_queue.put_nowait(response.data)  # type: ignore[union-attr]
                if response.tool_call:
                    await self._handle_tool_call(response.tool_call)
                sc = response.server_content
                if sc:
                    if sc.output_transcription and sc.output_transcription.text:
                        print(sc.output_transcription.text, end="", flush=True)
                    if sc.input_transcription and sc.input_transcription.text:
                        print(f"\nvocê: {sc.input_transcription.text}")
                    if sc.interrupted:
                        self._drain_playback()
            # End of a turn: drop any audio that was queued but not played (clean interrupts).
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
            samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16"
        )
        stream.start()
        try:
            while True:
                chunk = await self._audio_in_queue.get()  # type: ignore[union-attr]
                await asyncio.to_thread(stream.write, chunk)
        finally:
            stream.stop()
            stream.close()

    async def run(self) -> None:
        from google import genai

        load_env()
        import os

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("GEMINI_API_KEY não definida (veja o README / python/.env).", file=sys.stderr)
            return

        from google.genai import types

        live_cfg = self._cfg.get("live", {})
        model = live_cfg.get("model", "gemini-3.1-flash-live-preview")
        api_version = live_cfg.get("api_version", "v1beta")
        client = genai.Client(api_key=api_key, http_options={"api_version": api_version})
        config = _build_config(types, self._cfg)

        print(f"Conectando ao Live API ({model})... fale à vontade. Ctrl-C para sair.")
        try:
            async with (
                client.aio.live.connect(model=model, config=config) as session,
                asyncio.TaskGroup() as tg,
            ):
                self._session = session
                self._audio_in_queue = asyncio.Queue()
                self._out_queue = asyncio.Queue(maxsize=20)
                tg.create_task(self._listen_audio())
                tg.create_task(self._send_realtime())
                tg.create_task(self._receive())
                tg.create_task(self._play_audio())
        except Exception as exc:
            # Catches connect errors (plain) and task failures (ExceptionGroup). Surface the cause;
            # a bad live.model is the usual culprit — try another in config.yaml.
            print(f"\n[erro Live] {type(exc).__name__}: {exc}", file=sys.stderr)
            if isinstance(exc, BaseExceptionGroup):
                for sub in exc.exceptions:
                    print(f"  - {type(sub).__name__}: {sub}", file=sys.stderr)


def run_live(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg or load_config(None)
    face = TextFaceDisplay()  # MatrixFaceDisplay on the board (MAX7219 via Bridge)
    try:
        asyncio.run(LiveClippy(cfg, face).run())
    except KeyboardInterrupt:
        print("\nAté logo! 👋")
    return 0
