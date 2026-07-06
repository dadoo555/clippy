"""CLI entry point for Clippy.

Usage (with venv active, from the python/ folder):
  python -m clippy live              # real-time voice via the Gemini Live API (audio in/out)
  python -m clippy chat              # text conversation with Gemini (needs GEMINI_API_KEY)
  python -m clippy chat --dry-run    # offline echo, no API key needed (tests the plumbing)
  python -m clippy devices           # list audio devices
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

    session = ConversationSession(brain, TextIOChannel(), TextFaceDisplay())
    session.run()
    return 0


def _portaudio_hint(exc: Exception) -> str:
    return (
        f"Erro de áudio: {exc}\n"
        "Falta a biblioteca PortAudio (o sounddevice depende dela). Na placa (Debian):\n"
        "  sudo apt update && sudo apt install -y libportaudio2"
    )


def _cmd_live(args: argparse.Namespace) -> int:
    # Imported lazily so `chat` never loads the audio stack.
    try:
        from .live import run_live
    except OSError as exc:
        print(_portaudio_hint(exc), file=sys.stderr)
        return 1

    return run_live(load_config(args.config))


def _cmd_devices(args: argparse.Namespace) -> int:
    """List audio devices so you can pick a mic/speaker."""
    try:
        import sounddevice as sd
    except OSError as exc:
        print(_portaudio_hint(exc), file=sys.stderr)
        return 1

    print(sd.query_devices())
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Clippy: assistente de voz (Gemini).")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("live", help="Conversa por voz em tempo real (Gemini Live API)")

    chat_p = sub.add_parser("chat", help="Conversa por texto com o Gemini")
    chat_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo offline: ecoa a entrada sem chamar a API (não precisa de chave)",
    )

    sub.add_parser("devices", help="Lista os dispositivos de áudio")

    args = parser.parse_args(argv)
    if args.command == "live":
        return _cmd_live(args)
    if args.command == "chat":
        return _cmd_chat(args)
    if args.command == "devices":
        return _cmd_devices(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
