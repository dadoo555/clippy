"""Fixed catalog of face expressions.

Single source of truth for expression names. The MCU sketch's 8x8 bitmap table
(MAX7219, added in the face phase) must use exactly these names, and Gemini is
constrained to this enum via structured output so it can only pick valid faces.
"""

from __future__ import annotations

from enum import Enum


class Expression(str, Enum):
    """Face expressions shown on the MAX7219 8x8 matrix.

    The "emotional" values are chosen by Gemini per reply. `dormindo` is reserved
    for the SUSPENSO/DESLIGADO states and is set by the state machine, not by Gemini.
    """

    neutro = "neutro"
    feliz = "feliz"
    muito_feliz = "muito_feliz"
    triste = "triste"
    pensativo = "pensativo"
    surpreso = "surpreso"
    confuso = "confuso"
    piscada = "piscada"
    amoroso = "amoroso"
    dormindo = "dormindo"
