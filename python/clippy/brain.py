"""The conversational brain: Gemini with Google Search grounding and a face tag.

Input can be typed text or a recorded audio utterance. We do NOT use response_schema/JSON here
because it is incompatible with the google_search grounding tool; instead the model ends each
reply with a `[[face:nome]]` tag that we parse out. History is kept in memory and resent every
turn (bounded window), so the conversation has normal memory that resets when the program restarts.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .env import load_env
from .expressions import Expression
from .io_channel import AudioInput

# Keep at most this many history entries (user+model each count as one) to bound token cost.
_MAX_HISTORY = 24

# Appended to the persona in code so the face tag works even with an old local_config.yaml.
_EXPR_NAMES = ", ".join(e.value for e in Expression)
_FACE_INSTRUCTION = (
    "Ao final de CADA resposta, escreva a expressão de rosto que combina, exatamente no formato "
    f"[[face:NOME]] (colchetes duplos), onde NOME é uma destas: {_EXPR_NAMES}. "
    "Não comente a tag; apenas coloque-a no fim. Exemplo: 'Claro, posso ajudar! [[face:feliz]]'"
)


@dataclass
class ClippyReply:
    text: str
    expression: Expression


_FALLBACK = ClippyReply(text="Ops, me perdi aqui, pode repetir?", expression=Expression.confuso)


def _parse_face(raw: str) -> ClippyReply:
    """Split the model text into spoken text + expression from the [[face:nome]] tag."""
    expr = Expression.neutro
    m = re.search(r"\[\[\s*face\s*:\s*(\w+)\s*\]\]", raw, re.IGNORECASE)
    if m:
        try:
            expr = Expression(m.group(1).lower())
        except ValueError:
            pass
    clean = re.sub(r"\[\[\s*face\s*:\s*\w+\s*\]\]", "", raw, flags=re.IGNORECASE).strip()
    return ClippyReply(text=clean or raw.strip(), expression=expr)


@runtime_checkable
class Brain(Protocol):
    def reply(self, user_input: "str | AudioInput") -> ClippyReply: ...


class ClippyBrain:
    """Gemini-backed brain with web search. Reads GEMINI_API_KEY from the environment."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        load_env()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY não está definida. Pegue uma chave grátis no Google AI Studio "
                "(https://aistudio.google.com/apikey) e defina de um destes jeitos:\n"
                "  1. (recomendado) crie python/.env a partir de python/.env.example com:\n"
                "         GEMINI_API_KEY=sua-chave\n"
                '  2. PowerShell:  $env:GEMINI_API_KEY = "sua-chave"\n'
                '  3. bash/Debian: export GEMINI_API_KEY="sua-chave"'
            )

        from google import genai
        from google.genai import types

        self._types = types
        gemini_cfg = cfg.get("gemini", {})
        self._model = gemini_cfg.get("model", "gemini-2.5-flash")
        self._client = genai.Client(api_key=api_key)

        persona = gemini_cfg.get("persona", "")
        tools = []
        if gemini_cfg.get("web_search", True):
            # Real-time grounding so facts/weather/news are not hallucinated.
            tools.append(types.Tool(google_search=types.GoogleSearch()))

        self._config = types.GenerateContentConfig(
            system_instruction=persona + "\n\n" + _FACE_INSTRUCTION,
            temperature=gemini_cfg.get("temperature", 0.7),
            max_output_tokens=gemini_cfg.get("max_output_tokens", 512),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            tools=tools,
        )
        self._history: list[Any] = []

    def reply(self, user_input: "str | AudioInput") -> ClippyReply:
        types = self._types
        if isinstance(user_input, AudioInput):
            parts = [types.Part.from_bytes(data=user_input.data, mime_type=user_input.mime_type)]
        else:
            parts = [types.Part(text=user_input)]
        user_content = types.Content(role="user", parts=parts)

        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=self._history + [user_content],
                config=self._config,
            )
        except Exception as exc:
            print(f"[erro Gemini] {type(exc).__name__}: {exc}", file=sys.stderr)
            return _FALLBACK

        raw = getattr(resp, "text", None)
        if not raw:
            print("[erro Gemini] resposta vazia (possível bloqueio de segurança).", file=sys.stderr)
            return _FALLBACK

        reply = _parse_face(raw)
        # Keep the real turn in history (audio included) so memory works; trim to bound cost.
        self._history.append(user_content)
        self._history.append(types.Content(role="model", parts=[types.Part(text=reply.text)]))
        self._history = self._history[-_MAX_HISTORY:]
        return reply

    @property
    def history(self) -> Any:
        return self._history


class EchoBrain:
    """Offline stub for --dry-run: echoes input with a neutral face, no API call."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self._history: list[tuple[str, str]] = []

    def reply(self, user_input: "str | AudioInput") -> ClippyReply:
        heard = "[áudio]" if isinstance(user_input, AudioInput) else str(user_input)
        reply = ClippyReply(text=f"(eco) {heard}", expression=Expression.neutro)
        self._history.append(("user", heard))
        self._history.append(("clippy", reply.text))
        return reply

    @property
    def history(self) -> list[tuple[str, str]]:
        return self._history
