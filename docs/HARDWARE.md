# Face hardware — MAX7219 8×8 on Arduino UNO Q

Wiring and firmware guide for Clippy's face: an **ELEGOO MAX7219 Dot Matrix Module V02**
(8×8 LED panel) driven by the **MCU (STM32U585)** over SPI. Python (MPU) picks the expression and sends the
**name** over the **Arduino Router Bridge**; the sketch stores the bitmaps and draws on the matrix.

---

## ⚡ Do you need Arduino code?

**Yes.** The matrix is controlled by the MCU — Python alone cannot talk to it. You flash **once**
the sketch [`arduino/clippy_face/clippy_face.ino`](../arduino/clippy_face/clippy_face.ino) on the
MCU (via Arduino IDE), and from then on the Python side only calls:

```python
Bridge.call("set_face", "feliz")   # any value from clippy/expressions.py
Bridge.call("clippy_ping")         # -> 1 if the sketch is loaded
```

---

## 🔌 Wiring (1 module, recommended)

The Uno Q runs at **3.3V** (pins are 5V-tolerant on input, but HIGH output is 3.3V).
For the MAX7219 to recognize the logic level **within spec without a level shifter**, power
the module from the **3V3** pin (not 5V). With a single module showing a small face, current draw is
low and 3V3 is enough.

Connect to the module **INPUT** side (the one with **DIN**; the **DOUT** side is only for chaining
more modules and stays unconnected here):

| MAX7219 (input side) | UNO Q pin | Function |
| --- | --- | --- |
| **VCC** | **3V3** | 3.3V power (keeps logic within spec) |
| **GND** | **GND** | Common ground |
| **DIN** | **D11** | Data (MOSI) |
| **CS**  | **D10** | Latch/load (SS) |
| **CLK** | **D13** | Clock (SCK) |

> Tip: if the face appears **upside down or mirrored**, do not change the wiring — adjust
> `FLIP_ROWS` / `MIRROR_COLS` at the top of the `.ino` and reflash.

### Want maximum brightness? (optional)

If the matrix looks dim, or if you chain several modules later, power **VCC → 5V** and
add a **3.3V→5V level shifter** on **DIN, CS, CLK** (e.g. a level-shift shield for
Uno Q). Do not connect 5V directly to the matrix expecting reliable logic at 3.3V — the MAX7219
HIGH threshold at 5V is ~3.5V, above what the Uno Q outputs.

---

## 🧰 Flash the firmware (one time)

1. On your PC, open **Arduino IDE** and select the **Arduino UNO Q** (MCU) board.
2. Install libraries via **Library Manager**:
   - **LedControl** (by Eberhard Fahle) — MAX7219 driver.
   - **Arduino_RouterBridge** — MessagePack RPC MPU⇄MCU.
3. Open `arduino/clippy_face/clippy_face.ino` and **upload** to the MCU.
4. On the board's Linux, make sure the router is running:
   ```bash
   sudo systemctl start arduino-router
   sudo systemctl enable arduino-router
   ```
5. Test from the board (Python):
   ```python
   from arduino.app_utils import Bridge
   Bridge.call("set_face", "feliz")     # the face should change
   print(Bridge.call("clippy_ping"))    # -> 1
   ```

---

## 🐍 Wiring up the Python side

The expression catalog is [`python/clippy/expressions.py`](../python/clippy/expressions.py) — the
names there (`feliz`, `triste`, `pensativo`, …) are **the same** as in the `FACES[]` table in the `.ino`.
When you hook up the real matrix (face phase), [`python/clippy/face.py`](../python/clippy/face.py)
already provides `MatrixFaceDisplay`, which only calls the Bridge:

```python
class MatrixFaceDisplay:
    def __init__(self):
        from arduino.app_utils import Bridge   # only exists in App Lab runtime on the board
        self._Bridge = Bridge
    def set_expression(self, expression):
        self._Bridge.call("set_face", expression.value)
```

`live` mode (`clippy/live.py`) already uses `build_face("auto")`: if the Bridge responds, it drives the
matrix **and** prints to the terminal; otherwise it falls back to terminal only with a warning.

### Making the venv see the Bridge (`arduino.app_utils`)

The `arduino.app_utils` module comes from the **board's App Lab** (`arduino_app_bricks` package) and is **not on
PyPI** — `pip install` cannot find it. If you run Clippy in your own venv, point it at the
`site-packages` of an App Lab project that already has the package (e.g. a sibling project), with a `.pth`:

```bash
echo /home/arduino/OUTRO-PROJETO/python/.venv/lib/python3.13/site-packages > \
  ~/clippy/python/.venv/lib/python3.13/site-packages/_arduino_bridge.pth
# test:
python -c "from arduino.app_utils import Bridge; print(Bridge.call('clippy_ping', timeout=3))"  # -> 1
```

Clippy's own packages take priority, so the `.pth` only fills in what is missing (`arduino` and
its deps). Alternative: `pip install arduino-app-bricks` **if** you have the App Lab index
configured; or create the venv inside the App Lab workflow.

> ⚠️ When adding/renaming an expression in `expressions.py`, add the matching bitmap in
> `FACES[]` in the `.ino` with **the same name**. Unknown names fall back to the `neutro` face.
