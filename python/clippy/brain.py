"""The conversational brain: Gemini with structured {text, expression} output.

`ClippyBrain` keeps the chat history in memory (the google-genai chat session resends
it every turn) and constrains the model to the fixed `Expression` catalog via a Pydantic
response schema. `EchoBrain` is an offline stub for `--dry-run` (no API key needed).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from .env import load_env
from .expressions import Expression


class ClippyReply(BaseModel):
    """One turn of Clippy's answer: what to say and which face to show."""

    text: str
    expression: Expression


# Spoken-friendly fallback used when the API call fails or returns nothing parseable.
_FALLBACK = ClippyReply(text="Ops, me perdi aqui, pode repetir?", expression=Expression.confuso)


def _salvage_reply(raw: str) -> ClippyReply | None:
    """Recover a usable reply from truncated/partial JSON (e.g. cut off before the closing brace)."""
    match = re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if not match:
        return None
    try:
        text = json.loads(f'"{match.group(1)}"')  # decode \n, \" etc.
    except json.JSONDecodeError:
        return None
    expr = Expression.neutro
    em = re.search(r'"expression"\s*:\s*"(\w+)"', raw)
    if em:
        try:
            expr = Expression(em.group(1))
        except ValueError:
            pass
    return ClippyReply(text=text, expression=expr)


@runtime_checkable
class Brain(Protocol):
    """A source of Clippy replies. Text now, same interface once voice is added."""

    def reply(self, user_text: str) -> ClippyReply: ...


class ClippyBrain:
    """Gemini-backed brain. Reads GEMINI_API_KEY from the environment (never hardcoded)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        load_env()  # populate os.environ from python/.env if present
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

        # Imported here so `--dry-run` works even without google-genai installed.
        from google import genai
        from google.genai import types

        gemini_cfg = cfg.get("gemini", {})
        self._model = gemini_cfg.get("model", "gemini-2.5-flash")

        # Keep the client on self: if it is only a local, GC closes its HTTP transport and the
        # chat then fails with "Cannot send a request, as the client has been closed."
        self._client = genai.Client(api_key=api_key)
        # A chat session keeps history in memory and resends it on every send_message().
        self._chat = self._client.chats.create(
            model=self._model,
            config=types.GenerateContentConfig(
                system_instruction=gemini_cfg.get("persona", ""),
                temperature=gemini_cfg.get("temperature", 0.7),
                max_output_tokens=gemini_cfg.get("max_output_tokens", 512),
                # Disable "thinking": on 2.5-flash it eats the token budget and truncates the
                # JSON reply. Short spoken answers don't need it, and it's faster without it.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
                response_schema=ClippyReply,
            ),
        )

    def reply(self, user_text: str) -> ClippyReply:
        """Send one user turn, return the parsed {text, expression}. Never raises on API errors.

        On failure it prints the real reason to stderr so problems are visible instead of
        silently turning every turn into the fallback face.
        """
        try:
            resp = self._chat.send_message(user_text)
        except Exception as exc:
            print(f"[erro Gemini] {type(exc).__name__}: {exc}", file=sys.stderr)
            return _FALLBACK

        parsed = getattr(resp, "parsed", None)
        if isinstance(parsed, ClippyReply):
            return parsed

        # parsed came back empty: try strict JSON, then salvage a truncated reply, else report.
        raw = getattr(resp, "text", None)
        if raw:
            try:
                return ClippyReply.model_validate_json(raw)
            except Exception:
                salvaged = _salvage_reply(raw)
                if salvaged is not None:
                    return salvaged
                print(f"[erro parse] resposta incompleta | bruto: {raw!r}", file=sys.stderr)
        else:
            print("[erro Gemini] resposta vazia (sem texto) — possível bloqueio de segurança "
                  "ou modelo/schema não suportado.", file=sys.stderr)
        return _FALLBACK

    @property
    def history(self) -> Any:
        """The chat history (for future use: on-screen text, debugging)."""
        return self._chat.get_history()


class EchoBrain:
    """Offline stub for --dry-run: echoes input with a neutral face, no API call."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self._history: list[tuple[str, str]] = []

    def reply(self, user_text: str) -> ClippyReply:
        self._history.append(("user", user_text))
        reply = ClippyReply(text=f"(eco) {user_text}", expression=Expression.neutro)
        self._history.append(("clippy", reply.text))
        return reply

    @property
    def history(self) -> list[tuple[str, str]]:
        return self._history
