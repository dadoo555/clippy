/*
 * Clippy face — Arduino UNO Q (STM32U585 MCU) driving an ELEGOO MAX7219 8x8 LED matrix.
 *
 * Python on the MPU picks the expression and sends its name over the Arduino Router Bridge:
 *   from arduino.app_utils import Bridge
 *   Bridge.call("set_face", "feliz")   # any Expression value from clippy/expressions.py
 *   Bridge.call("clippy_ping")         # -> 1 when this sketch is loaded
 *
 * Requires arduino-router running on Linux (systemctl start arduino-router).
 *
 * Wiring (single module, power the matrix from 3V3 so 3.3V logic is in spec — no level shifter):
 *   MAX7219 (INPUT side) -> UNO Q
 *     VCC -> 3V3
 *     GND -> GND
 *     DIN -> D11
 *     CS  -> D10
 *     CLK -> D13
 *   (DOUT on the output side is only for chaining more modules — leave it free here.)
 *
 * Library: install "LedControl" (by Eberhard Fahle) via the Library Manager.
 * LedControl uses software SPI, so the exact pins are flexible; we keep the SPI-standard pins.
 */

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <LedControl.h>

// LedControl(dataPin=DIN, clkPin=CLK, csPin=CS, numDevices)
static const int PIN_DIN = 11;
static const int PIN_CLK = 13;
static const int PIN_CS  = 10;
static LedControl lc(PIN_DIN, PIN_CLK, PIN_CS, 1);

// Brightness 0..15. Keep it modest so the 3V3 rail is not stressed.
static const int FACE_INTENSITY = 3;

// If the physical module is mounted rotated/mirrored, flip these to fix orientation.
static const bool FLIP_ROWS = false;     // top<->bottom
static const bool MIRROR_COLS = false;   // left<->right

/*
 * Each face is 8 rows, top -> bottom. In every byte, bit7 = leftmost column, bit0 = rightmost.
 * These are easy to edit: draw the pixels you want and read the byte left-to-right.
 */
struct Face {
  const char* name;
  uint8_t rows[8];
};

static const Face FACES[] = {
  { "neutro", {
    0b00000000,
    0b01100110,  // eyes
    0b01100110,
    0b00000000,
    0b00000000,
    0b01111110,  // flat mouth
    0b00000000,
    0b00000000 } },
  { "feliz", {
    0b00000000,
    0b01100110,  // eyes
    0b01100110,
    0b00000000,
    0b00000000,
    0b10000001,  // smile: corners up
    0b01000010,
    0b00111100 } },
  { "muito_feliz", {
    0b01100110,  // arched eyes
    0b01100110,
    0b00000000,
    0b00000000,
    0b01111110,  // big open grin
    0b01000010,
    0b01000010,
    0b00111100 } },
  { "triste", {
    0b00000000,
    0b01100110,  // eyes
    0b01100110,
    0b00000000,
    0b00000000,
    0b00111100,  // frown: corners down
    0b01000010,
    0b10000001 } },
  { "pensativo", {
    0b00000000,
    0b01100110,  // eyes
    0b01100110,
    0b00000000,
    0b00000000,
    0b00000000,
    0b00111000,  // small mouth off to one side
    0b00000000 } },
  { "surpreso", {
    0b00000000,
    0b01100110,  // wide eyes
    0b01100110,
    0b00000000,
    0b00011000,  // round "O" mouth
    0b00100100,
    0b00100100,
    0b00011000 } },
  { "confuso", {
    0b00000000,
    0b01000110,  // uneven eyes
    0b01100100,
    0b00000000,
    0b00000000,
    0b00101010,  // wavy mouth
    0b00010100,
    0b00000000 } },
  { "piscada", {
    0b00000000,
    0b01100000,  // left eye open
    0b01100110,  // right eye winking (dash)
    0b00000000,
    0b00000000,
    0b10000001,  // smile
    0b01000010,
    0b00111100 } },
  { "amoroso", {
    0b00000000,
    0b01100110,  // heart
    0b11111111,
    0b11111111,
    0b01111110,
    0b00111100,
    0b00011000,
    0b00000000 } },
  { "dormindo", {
    0b00000000,
    0b00000000,
    0b01100110,  // closed eyes (dashes)
    0b00000000,
    0b00000000,
    0b00111100,  // calm small mouth
    0b00000000,
    0b00000000 } },
};
static const size_t FACE_COUNT = sizeof(FACES) / sizeof(FACES[0]);

static uint8_t reverseBits(uint8_t b) {
  b = (b & 0xF0) >> 4 | (b & 0x0F) << 4;
  b = (b & 0xCC) >> 2 | (b & 0x33) << 2;
  b = (b & 0xAA) >> 1 | (b & 0x55) << 1;
  return b;
}

static void drawFace(const uint8_t rows[8]) {
  for (int r = 0; r < 8; r++) {
    uint8_t value = rows[r];
    if (MIRROR_COLS) value = reverseBits(value);
    int target = FLIP_ROWS ? (7 - r) : r;
    lc.setRow(0, target, value);
  }
}

static const Face* findFace(const String& name) {
  for (size_t i = 0; i < FACE_COUNT; i++) {
    if (name == FACES[i].name) return &FACES[i];
  }
  return &FACES[0];  // unknown name -> neutro
}

// Bridge RPC: draw the named expression. Unknown names fall back to "neutro".
static void set_face_impl(String name) {
  drawFace(findFace(name)->rows);
}

// Bridge RPC: liveness check for the Python side.
static int clippy_ping_impl() {
  return 1;
}

void setup() {
  lc.shutdown(0, false);          // wake the MAX7219 from power-saving
  lc.setIntensity(0, FACE_INTENSITY);
  lc.clearDisplay(0);
  drawFace(findFace("dormindo")->rows);  // boot with the sleeping face

  Bridge.begin();
  (void)Bridge.provide_safe("set_face", set_face_impl);
  (void)Bridge.provide_safe("clippy_ping", clippy_ping_impl);
}

void loop() {
  delay(5);
}
