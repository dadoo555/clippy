"""Face display: shows the current expression.

Separate subsystem from speech because on the real device the face is the MAX7219 8x8 matrix
driven by the MCU (via Arduino Router Bridge), while speech comes out of the USB speaker via the
MPU. `TextFaceDisplay` prints to the terminal; `MatrixFaceDisplay` drives the physical matrix;
`MultiFace` does both. Used by the brain/model (emotion) and the state machine (state, e.g. dormindo).
"""

from __future__ import annotations

import sys
from typing import Protocol, runtime_checkable

from .expressions import Expression


@runtime_checkable
class FaceDisplay(Protocol):
    def set_expression(self, expression: Expression) -> None: ...


class TextFaceDisplay:
    """Print the chosen expression to the terminal."""

    def set_expression(self, expression: Expression) -> None:
        print(f"[carinha: {expression.value}]")


class MatrixFaceDisplay:
    """Draw the expression on the MAX7219 8x8 matrix via the MCU (Arduino Router Bridge).

    The MCU sketch (arduino/clippy_face) exposes `set_face(name)`; names match Expression values.
    Requires the arduino-router service running and the sketch flashed on the MCU.
    """

    def __init__(self) -> None:
        # arduino.app_utils only exists in the App Lab runtime on the UNO Q.
        from arduino.app_utils import Bridge

        self._Bridge = Bridge
        # Fail fast if the MCU/sketch/bridge isn't reachable, so we can fall back to text.
        self._Bridge.call("clippy_ping", timeout=3)

    def set_expression(self, expression: Expression) -> None:
        try:
            self._Bridge.call("set_face", expression.value, timeout=3)
        except Exception as exc:
            print(f"[erro matriz] {type(exc).__name__}: {exc}", file=sys.stderr)


class MultiFace:
    """Forward the expression to several displays (e.g. terminal + physical matrix)."""

    def __init__(self, *faces: FaceDisplay) -> None:
        self._faces = [f for f in faces if f is not None]

    def set_expression(self, expression: Expression) -> None:
        for f in self._faces:
            f.set_expression(expression)


def build_face(kind: str = "auto") -> FaceDisplay:
    """Build the face display. `kind`: 'auto' (matrix if reachable, else text), 'matrix', or 'text'.

    'auto'/'matrix' always keep the terminal print too, so you can see the expression on screen.
    """
    text = TextFaceDisplay()
    if kind == "text":
        return text

    try:
        matrix = MatrixFaceDisplay()
    except Exception as exc:
        print(f"[aviso] matriz MAX7219 indisponível ({type(exc).__name__}: {exc}); usando só o "
              "terminal. Verifique: sketch gravado no MCU, `sudo systemctl start arduino-router`, "
              "e que o Python enxerga `arduino.app_utils`.", file=sys.stderr)
        return text
    print("Matriz MAX7219 conectada (Bridge OK).")
    return MultiFace(text, matrix)
