# Clippy — Voice Assistant for the Arduino UNO Q

**Clippy** is a fun, animated assistant that runs **entirely on the Arduino UNO Q**.
The end goal: it listens for the word **"clippy"**, you speak, your speech goes to **Gemini**, and it
responds **by voice** — with an **LED face** (MAX7219 8×8 matrix) that reacts to what is being
said. The face expression is chosen by **Gemini itself** on every response.

Today Clippy already **holds real-time voice conversations** (Gemini Live API): it sleeps while listening for
**"clippy"**, wakes up, converses over audio (with web search and a face chosen by Gemini), and
**goes back to sleep after 10 s** of silence. Still missing: the physical LED matrix (the sketch already exists) and the
MCU button.

---

## 🔑 Get and configure your Gemini API key

1. Go to **Google AI Studio** (https://aistudio.google.com/apikey) and create a free **API key**
   (starts with `AIza...`).
2. Provide the key to the app. It never lives in code; the app reads it from `GEMINI_API_KEY`. Priority
   order: **real environment variable → `.env` file**.

**Recommended approach (dev and prod) — `.env` file:** copy `python/.env.example` to
`python/.env` and fill it in. `.env` is gitignored and loaded automatically at startup, so you
do not need to set `$env:`/`export` every time.

```bash
cd python
cp .env.example .env        # Windows PowerShell: copy .env.example .env
# edit .env and set: GEMINI_API_KEY=AIza...
```

**Alternative (environment variable):** useful when the key comes from the system/CI. Because it takes
priority over `.env`, it can override in production.
- **PowerShell (Windows):** `$env:GEMINI_API_KEY = "your-key"` (only for the current window)
- **bash (UNO Q Debian / Linux):** `export GEMINI_API_KEY="your-key"`

**On the board in production (systemd):** point the service at the same `.env`:
`EnvironmentFile=/path/to/clippy/python/.env`.

---

## 📦 Install

On the MPU Debian (or on your PC for development):

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🎤 Run by voice (Gemini Live API)

The main path: **real-time conversation**, audio in and audio out. You speak, Clippy
**responds by talking** with Gemini's native voice, with interruptions and web search.

```bash
python -m clippy devices   # list mic/speaker (to pick in config if needed)
python -m clippy live      # real-time voice conversation (requires GEMINI_API_KEY)
```

How it works:
- **Sleeps listening for "clippy"** (Vosk, local, offline — no API cost). When heard, it wakes and connects.
- **Audio↔audio streaming** via `client.aio.live.connect()` (mic at 16 kHz → Gemini → voice at 24 kHz).
- **Goes back to sleep after 10 s of silence** (`live.inactivity_timeout_s`).
- **Web search** (`gemini.web_search`) — weather/news/real facts, not made up.
- **Face chosen by Gemini** via the `set_face` function; today it prints to the terminal, and will drive the
  MAX7219 over the Bridge in the face phase.
- `Ctrl-C` exits. With no wake word configured, it runs one direct session and ends on timeout.

### Wake word "clippy" (Vosk)

You need a small Vosk model (offline, one-time setup):
1. Download a small model from https://alphacephei.com/vosk/models — e.g. **`vosk-model-small-pt-0.3`**
   (PT, ~50 MB). Unzip it.
2. Point to the **folder** in `config.yaml` → `wake.model_path: "C:/.../vosk-model-small-pt-0.3"`.
3. Run `python -m clippy live`. If `wake.model_path` is empty, the wake word is off and it
   goes straight into a session.

Vosk transcribes on top and matches any word from the `wake.phrases` list (default: `clip, clipe,
clipi, clippy, clique`) — adjust if it wakes too little or too often.

### Where model instructions live (persona)

In `config.yaml` → `gemini.persona`. That text is the **system prompt** and applies to both modes
(`live` and `chat`). That is where you define personality, language, and style.

Other settings (`config.yaml`): `live.model`/`voice`/`inactivity_timeout_s`, `gemini.web_search`,
`live.input_device`/`output_device`. If `live.model` errors for your key, change it (the comment
in config lists alternatives).

> ⚠️ **Deleted `local_config.yaml`?** Good — it is recreated from `config.yaml` on the next
> run, already with the `live` and `wake` sections.

## 💬 Run by text (optional, for testing)

```bash
python -m clippy chat            # text chat with Gemini (requires the key)
python -m clippy chat --dry-run  # offline: echoes input, no key or internet
```

Useful to validate key/persona without audio. Type `sair` (or `Ctrl-D`) to exit.

**Extra dependency on the board (Debian):** `sounddevice` needs PortAudio
(`sudo apt install libportaudio2`).

---

## 🙂 The face (hardware)

The face is an **ELEGOO MAX7219 Dot Matrix Module V02** (**8×8** LED panel), driven by the
**MCU (STM32U585)** over **SPI** — pins `VCC`, `GND`, `DIN`, `CS`, `CLK` (`DOUT` is only for
chaining multiple modules; with a single one, leave it unconnected). The expression catalog lives in
[`python/clippy/expressions.py`](python/clippy/expressions.py) and is the **single source** of names: the
MCU sketch's 8×8 bitmap table uses exactly those names.

**Wiring, firmware, and voltage:** see [`docs/HARDWARE.md`](docs/HARDWARE.md). The MCU sketch is already at
[`arduino/clippy_face/clippy_face.ino`](arduino/clippy_face/clippy_face.ino).

Microphone and speaker are **USB**, seen by **MPU Debian** — the audio pipeline
runs entirely on the MPU.

---

## 🧩 Code layout (extension points)

| File | Role |
|---|---|
| `clippy/live.py` | **Main mode:** real-time voice + state machine (sleep/wake/timeout) |
| `clippy/wake.py` | Offline "clippy" wake word (Vosk) |
| `clippy/brain.py` | Text mode: Gemini + search + face via `[[face:...]]` tag |
| `clippy/face.py` | Shows the expression (terminal now → `MatrixFaceDisplay` on MAX7219) |
| `clippy/expressions.py` | Fixed face catalog (mirrored in MCU bitmaps) |
| `clippy/session.py`, `io_channel.py` | Text mode loop and I/O |

---

## 🗺️ Roadmap

1. **Base:** text chat with Gemini + expression choice. ✅
2. **Real-time voice:** Gemini Live API (audio↔audio, search, face via `set_face`). ✅
3. **Wake word + states:** word "clippy" (Vosk), sleep/wake, 10 s timeout. ✅
   Still missing: physical **MCU button** (on/off).
4. **Face:** MCU sketch driving MAX7219 8×8 via Arduino Router Bridge (`MatrixFaceDisplay`).
5. **Polish:** board LEDs/matrix, latency, persona/voice tuning.
