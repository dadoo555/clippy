"""The conversation loop.

This is the single place the Phase 3 state machine (SUSPENSO/OUVINDO/PENSANDO/FALANDO
+ 30s timer) will replace, without touching brain/io/face.
"""

from __future__ import annotations

import re

from .brain import Brain
from .face import FaceDisplay
from .io_channel import IOChannel

# Words that end the conversation when said/typed alone.
_EXIT_WORDS = {"sair", "tchau", "quit", "exit"}


def _is_exit(text: str) -> bool:
    # Strip punctuation/casing so voice transcriptions like "Tchau." also match.
    return re.sub(r"[^\w]", "", text.lower()) in _EXIT_WORDS


class ConversationSession:
    def __init__(self, brain: Brain, io: IOChannel, face: FaceDisplay) -> None:
        self._brain = brain
        self._io = io
        self._face = face

    def run(self) -> None:
        print("Clippy pronto! (digite 'sair' ou Ctrl-D para encerrar)\n")
        try:
            while True:
                user_text = self._io.get_user_input()
                if user_text is None:  # EOF
                    break
                user_text = user_text.strip()
                if not user_text:
                    continue
                if _is_exit(user_text):
                    break

                reply = self._brain.reply(user_text)
                self._face.set_expression(reply.expression)
                self._io.speak(reply.text)
        except KeyboardInterrupt:
            pass
        print("\nAté logo! 👋")
