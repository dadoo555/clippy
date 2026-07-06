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
 *
 * ANIMATION: each face is a list of 8x8 frames. Faces with a single frame are static; faces with
 * more than one frame animate — loop() advances the frame every `frameMs` using millis() (never
 * blocks, so the Bridge keeps responding). set_face just switches the active face and restarts it.
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
 * Each frame is 8 rows, top -> bottom. In every byte, bit7 = leftmost column, bit0 = rightmost.
 * Draw the pixels you want and read the byte left-to-right. A face is one or more frames plus a
 * per-frame duration (ms); animated faces cycle through their frames forever.
 */
struct Frame {
  uint8_t rows[8];
};

struct Face {
  const char* name;
  const Frame* frames;
  uint8_t frameCount;
  uint16_t frameMs;   // how long each frame is shown; ignored when frameCount == 1
};

// ---- Static faces (single frame) -------------------------------------------------------------

static const Frame FR_NEUTRO[] = {{{
  0b00000000,
  0b01100110,  // eyes
  0b01100110,
  0b00000000,
  0b00000000,
  0b01111110,  // flat mouth
  0b00000000,
  0b00000000 }}};

static const Frame FR_FELIZ[] = {{{
  0b00000000,
  0b01100110,  // eyes
  0b01100110,
  0b00000000,
  0b00000000,
  0b10000001,  // smile: corners up
  0b01000010,
  0b00111100 }}};

static const Frame FR_MUITO_FELIZ[] = {{{
  0b01100110,  // arched eyes
  0b01100110,
  0b00000000,
  0b00000000,
  0b01111110,  // big open grin
  0b01000010,
  0b01000010,
  0b00111100 }}};

static const Frame FR_TRISTE[] = {{{
  0b00000000,
  0b01100110,  // eyes
  0b01100110,
  0b00000000,
  0b00000000,
  0b00111100,  // frown: corners down
  0b01000010,
  0b10000001 }}};

static const Frame FR_PENSATIVO[] = {{{
  0b00000000,
  0b01100110,  // eyes
  0b01100110,
  0b00000000,
  0b00000000,
  0b00000000,
  0b00111000,  // small mouth off to one side
  0b00000000 }}};

static const Frame FR_SURPRESO[] = {{{
  0b00000000,
  0b01100110,  // wide eyes
  0b01100110,
  0b00000000,
  0b00011000,  // round "O" mouth
  0b00100100,
  0b00100100,
  0b00011000 }}};

static const Frame FR_BRAVO[] = {{{
  0b01000010,  // angry brows: outer high...
  0b00100100,  // ...inner low (V shape)
  0b01100110,  // eyes
  0b00000000,
  0b00000000,
  0b00111100,  // frown
  0b01000010,
  0b00000000 }}};

static const Frame FR_CARETA[] = {{{
  0b00000000,
  0b00000110,  // wink: left eye closed, right open
  0b01100110,
  0b00000000,
  0b10000001,  // smile
  0b01000010,
  0b00111100,
  0b00011000 }}};  // tongue sticking out

static const Frame FR_ENTEDIADO[] = {{{
  0b00000000,
  0b00000000,
  0b01100110,  // heavy lids (line)
  0b00100100,  // small tired eyes
  0b00000000,
  0b00000000,
  0b01111110,  // flat, unimpressed mouth
  0b00000000 }}};

static const Frame FR_ASSUSTADO[] = {{{
  0b01000010,  // raised brows
  0b00000000,
  0b01100110,  // wide staring eyes
  0b01100110,
  0b00000000,
  0b00011000,  // small worried mouth
  0b00011000,
  0b00000000 }}};

static const Frame FR_LEGAL[] = {{{
  0b00000000,
  0b11111111,  // sunglasses brow bar
  0b01100110,  // lenses (two blocks with a gap)
  0b00000000,
  0b00000000,
  0b10000001,  // cool smile
  0b01000010,
  0b00111100 }}};

// ---- Animated faces (multiple frames) --------------------------------------------------------

// piscada: open eyes + smile <-> wink.
static const Frame FR_PISCADA[] = {
  {{ 0b00000000,
     0b01100110,  // both eyes open
     0b01100110,
     0b00000000,
     0b00000000,
     0b10000001,  // smile
     0b01000010,
     0b00111100 }},
  {{ 0b00000000,
     0b00000110,  // left eye closed...
     0b01100110,  // ...right eye still open (wink)
     0b00000000,
     0b00000000,
     0b10000001,
     0b01000010,
     0b00111100 }},
};

// amoroso: heartbeat — big heart <-> small heart.
static const Frame FR_AMOROSO[] = {
  {{ 0b00000000,
     0b01100110,  // big heart
     0b11111111,
     0b11111111,
     0b01111110,
     0b00111100,
     0b00011000,
     0b00000000 }},
  {{ 0b00000000,
     0b00000000,
     0b00100100,  // small heart
     0b01111110,
     0b01111110,
     0b00111100,
     0b00011000,
     0b00000000 }},
};

// rindo: laughing — mouth wide open <-> mouth smaller ("haha haha").
static const Frame FR_RINDO[] = {
  {{ 0b00000000,
     0b01100110,  // eyes
     0b01100110,
     0b00000000,
     0b01111110,  // wide open laughing mouth
     0b01111110,
     0b01111110,
     0b00111100 }},
  {{ 0b00000000,
     0b01100110,
     0b01100110,
     0b00000000,
     0b00000000,
     0b00111100,  // smaller open mouth
     0b00111100,
     0b00011000 }},
};

// chorando: crying — tears just below the eyes <-> tears fallen lower.
static const Frame FR_CHORANDO[] = {
  {{ 0b00000000,
     0b01100110,  // eyes
     0b01100110,
     0b01000010,  // tears starting
     0b00000000,
     0b00111100,  // frown
     0b01000010,
     0b00000000 }},
  {{ 0b00000000,
     0b01100110,
     0b01100110,
     0b00000000,
     0b01000010,  // tears falling
     0b00111100,
     0b01000010,
     0b01000010 }},  // tears reaching the bottom
};

// confuso: wavy mouth wobbling side to side + uneven eyes swapping.
static const Frame FR_CONFUSO[] = {
  {{ 0b00000000,
     0b01000110,  // uneven eyes
     0b01100100,
     0b00000000,
     0b00000000,
     0b00101010,  // wavy mouth
     0b00010100,
     0b00000000 }},
  {{ 0b00000000,
     0b01100100,  // eyes swapped
     0b01000110,
     0b00000000,
     0b00000000,
     0b00010101,  // wavy mouth shifted
     0b00101010,
     0b00000000 }},
};

// dormindo: sleeping — calm face <-> a little "z" rising in the corner.
static const Frame FR_DORMINDO[] = {
  {{ 0b00000000,
     0b00000000,
     0b00000000,
     0b01100110,  // closed eyes (dashes)
     0b00000000,
     0b00000000,
     0b00111100,  // calm small mouth
     0b00000000 }},
  {{ 0b00000111,  // z appears, top-right corner
     0b00000010,
     0b00000111,
     0b01100110,  // closed eyes
     0b00000000,
     0b00000000,
     0b00111100,
     0b00000000 }},
};

// Table of all faces. `frames`/`frameCount` come from the arrays above; `frameMs` sets the pace
// (only used when there is more than one frame). The first entry (neutro) is the unknown-name
// fallback, so keep it first.
static const Face FACES[] = {
  { "neutro",      FR_NEUTRO,      1, 0   },
  { "feliz",       FR_FELIZ,       1, 0   },
  { "muito_feliz", FR_MUITO_FELIZ, 1, 0   },
  { "triste",      FR_TRISTE,      1, 0   },
  { "pensativo",   FR_PENSATIVO,   1, 0   },
  { "surpreso",    FR_SURPRESO,    1, 0   },
  { "confuso",     FR_CONFUSO,     2, 350 },
  { "piscada",     FR_PISCADA,     2, 280 },
  { "amoroso",     FR_AMOROSO,     2, 450 },
  { "rindo",       FR_RINDO,       2, 200 },
  { "bravo",       FR_BRAVO,       1, 0   },
  { "chorando",    FR_CHORANDO,    2, 320 },
  { "careta",      FR_CARETA,      1, 0   },
  { "entediado",   FR_ENTEDIADO,   1, 0   },
  { "assustado",   FR_ASSUSTADO,   1, 0   },
  { "legal",       FR_LEGAL,       1, 0   },
  { "dormindo",    FR_DORMINDO,    2, 600 },
};
static const size_t FACE_COUNT = sizeof(FACES) / sizeof(FACES[0]);

// Currently displayed face and where we are in its animation.
static const Face* g_face = &FACES[0];
static uint8_t g_frameIdx = 0;
static unsigned long g_lastFrame = 0;

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

static void showCurrentFrame() {
  drawFace(g_face->frames[g_frameIdx].rows);
}

static const Face* findFace(const String& name) {
  for (size_t i = 0; i < FACE_COUNT; i++) {
    if (name == FACES[i].name) return &FACES[i];
  }
  return &FACES[0];  // unknown name -> neutro
}

// Bridge RPC: switch to the named expression and restart its animation from frame 0.
// Unknown names fall back to "neutro".
static void set_face_impl(String name) {
  g_face = findFace(name);
  g_frameIdx = 0;
  g_lastFrame = millis();
  showCurrentFrame();
}

// Bridge RPC: liveness check for the Python side.
static int clippy_ping_impl() {
  return 1;
}

void setup() {
  lc.shutdown(0, false);          // wake the MAX7219 from power-saving
  lc.setIntensity(0, FACE_INTENSITY);
  lc.clearDisplay(0);

  g_face = findFace("dormindo");  // boot with the sleeping face
  g_frameIdx = 0;
  g_lastFrame = millis();
  showCurrentFrame();

  Bridge.begin();
  (void)Bridge.provide_safe("set_face", set_face_impl);
  (void)Bridge.provide_safe("clippy_ping", clippy_ping_impl);
}

void loop() {
  // Advance the animation for multi-frame faces without ever blocking (millis()-based timing),
  // so the Bridge stays responsive between frames.
  if (g_face->frameCount > 1) {
    unsigned long now = millis();
    if (now - g_lastFrame >= g_face->frameMs) {
      g_lastFrame = now;
      g_frameIdx = (uint8_t)((g_frameIdx + 1) % g_face->frameCount);
      showCurrentFrame();
    }
  }
  delay(5);
}
