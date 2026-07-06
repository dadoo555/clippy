"""CLI entry point for Clippy.

Usage (with venv active, from the python/ folder):
  python -m clippy chat              # real Gemini conversation (needs GEMINI_API_KEY)
  python -m clippy chat --dry-run    # offline echo, no API key needed (tests the plumbing)
"""

from __future__ import annotations

import argparse
import sys

from .brain import Brain, ClippyBrain, EchoBrain
from .face import TextFaceDisplay
from .io_channel import TextIOChannel
from .session import ConversationSession
from .settings import load_config


def _force_utf8_output() -> None:
    """Portuguese accents and emojis must not crash on non-UTF-8 consoles (e.g. Windows cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _cmd_chat(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)

    brain: Brain
    if args.dry_run:
        brain = EchoBrain(cfg)
    else:
        try:
            brain = ClippyBrain(cfg)
        except RuntimeError as exc:
            # Clean message (e.g. missing API key) instead of a stack trace.
            print(str(exc), file=sys.stderr)
            return 1

    if args.voice:
        # Imported lazily so text mode never loads the heavy audio/STT stack.
        from .voice_channel import VoiceIOChannel

        io = VoiceIOChannel(cfg)
    else:
        io = TextIOChannel()

    session = ConversationSession(brain, io, TextFaceDisplay())
    session.run()
    return 0


def _cmd_devices(args: argparse.Namespace) -> int:
    """List audio devices so you can set voice.input_device / voice.output_device in config."""
    import sounddevice as sd

    print(sd.query_devices())
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Clippy: assistente de conversa (Fase 1, texto).")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    sub = parser.add_subparsers(dest="command", required=True)

    chat_p = sub.add_parser("chat", help="Loop de conversa com o Gemini (texto ou voz)")
    chat_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo offline: ecoa a entrada sem chamar a API (não precisa de chave)",
    )
    chat_p.add_argument(
        "--voice",
        action="store_true",
        help="Entrada por microfone (VAD + Whisper) e saída falada (TTS)",
    )

    sub.add_parser("devices", help="Lista os dispositivos de áudio (para escolher mic/alto-falante)")

    args = parser.parse_args(argv)
    if args.command == "chat":
        return _cmd_chat(args)
    if args.command == "devices":
        return _cmd_devices(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
