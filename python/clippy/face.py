"""Face display: shows the current expression.

Separate subsystem from speech because on the real device the face is the MAX7219 8x8
matrix driven by the MCU, while speech comes out of the USB speaker via the MPU. Phase 1
is a terminal stub; the face phase adds `MatrixFaceDisplay` calling `Bridge.call("set_face", ...)`.
Used both by the brain (emotion) and later by the state machine (state, e.g. `dormindo`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .expressions import Expression


@runtime_checkable
class FaceDisplay(Protocol):
    def set_expression(self, expression: Expression) -> None: ...


class TextFaceDisplay:
    """Phase 1: print the chosen expression to the terminal."""

    def set_expression(self, expression: Expression) -> None:
        print(f"[carinha: {expression.value}]")


class MatrixFaceDisplay:
    """Face phase: draw the expression on the MAX7219 8x8 matrix via the MCU (Arduino Router Bridge).

    The MCU sketch (arduino/clippy_face) exposes `set_face(name)`; names match Expression values.
    """

    def __init__(self) -> None:
        # arduino.app_utils only exists in the App Lab runtime on the UNO Q.
        from arduino.app_utils import Bridge

        self._Bridge = Bridge

    def set_expression(self, expression: Expression) -> None:
        self._Bridge.call("set_face", expression.value)
