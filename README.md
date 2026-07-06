# Clippy — Assistente de Voz para o Arduino UNO Q

O **Clippy** é um assistente animado e bem-humorado que roda **inteiramente no Arduino UNO Q**.
A meta final: ele ouve a palavra **"clippy"**, você fala, a fala vai pro **Gemini**, e ele
responde **por voz** — com um **rosto de LED** (matriz MAX7219 8×8) que reage ao que está sendo
dito. A expressão da carinha é escolhida pelo **próprio Gemini** a cada resposta.

Este repositório está na **Fase 1**: a fundação. Um loop de **conversa por texto** com o Gemini
que já devolve, a cada turno, **`{texto, expressão}`**. Voz (Whisper + Piper), a matriz de LED no
MCU e a máquina de estados entram nas próximas fases **sem reescrever** o núcleo.

---

## 🔑 Obter e configurar a chave do Gemini

1. Acesse o **Google AI Studio** (https://aistudio.google.com/apikey) e crie uma **API key**
   gratuita (começa com `AIza...`).
2. Forneça a chave ao app. Ela nunca fica no código; o app lê de `GEMINI_API_KEY`. Ordem de
   prioridade: **variável de ambiente real → arquivo `.env`**.

**Jeito recomendado (dev e prod) — arquivo `.env`:** copie `python/.env.example` para
`python/.env` e preencha. O `.env` é gitignored e é lido automaticamente no arranque, então você
não precisa mexer com `$env:`/`export` toda vez.

```bash
cd python
cp .env.example .env        # Windows PowerShell: copy .env.example .env
# edite .env e coloque: GEMINI_API_KEY=AIza...
```

**Alternativa (variável de ambiente):** útil quando a chave vem do sistema/CI. Como ela tem
prioridade sobre o `.env`, serve para sobrescrever em produção.
- **PowerShell (Windows):** `$env:GEMINI_API_KEY = "sua-chave"` (vale só na janela atual)
- **bash (Debian do UNO Q / Linux):** `export GEMINI_API_KEY="sua-chave"`

**Em produção na placa (systemd):** aponte o serviço para o mesmo `.env`:
`EnvironmentFile=/caminho/para/clippy/python/.env`.

---

## 📦 Instalar

No Debian do MPU (ou no PC para desenvolvimento):

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🎤 Rodar por voz (Gemini Live API)

O jeito principal: **conversa em tempo real**, áudio entra e áudio sai. Você fala, o Clippy
**responde falando** com a voz nativa do Gemini, com interrupções e busca na internet.

```bash
python -m clippy devices   # lista mic/alto-falante (para escolher no config, se precisar)
python -m clippy live      # conversa por voz em tempo real (precisa da GEMINI_API_KEY)
```

Fale à vontade; aperte `Ctrl-C` para sair. Como funciona:
- **Áudio↔áudio streaming** via `client.aio.live.connect()` (mic a 16 kHz → Gemini → voz a 24 kHz).
- **Busca na internet** (`gemini.web_search`) — clima/notícias/fatos reais, não inventados.
- **Carinha decidida pelo Gemini** por uma função `set_face` (o modelo a chama quando muda de
  humor); hoje imprime no terminal, e vira o MAX7219 pela Bridge na fase do rosto.
- **Memória** durante a sessão (janela deslizante nativa); zera ao reiniciar.

Ajustes em `config.yaml` (seção `live`): `model`, `voice` (timbre: Leda, Puck, Kore...),
`api_version`, `face_tool`. Se o modelo do padrão der erro para sua chave, troque `live.model`
(o comentário no config lista alternativas).

> ⚠️ Já tem um `python/local_config.yaml` antigo? Ele **não** traz a seção `live`. Apague-o (ele
> se recria a partir de `config.yaml`) para pegar as opções novas.

## 💬 Rodar por texto (opcional, para testar)

```bash
python -m clippy chat            # conversa por texto com o Gemini (precisa da chave)
python -m clippy chat --dry-run  # offline: ecoa a entrada, sem chave nem internet
```

Útil para validar chave/persona sem áudio. Digite `sair` (ou `Ctrl-D`) para encerrar.

Ajustes em `config.yaml` (seção `voice`): `stt_engine` (gemini/whisper), modelo do Whisper
(`stt.model`), sensibilidade (`silence_threshold`, `silence_ms`), dispositivos
(`input_device`/`output_device`) e TTS (`tts.engine`, `tts.edge_voice`). Para encerrar:
fale/**digite** "sair"/"tchau", ou `Ctrl-C`.

> Comparação Whisper local × áudio pro Gemini, e o plano do modo tempo-real (Live API), em
> [`docs/PLANO_LIVE_API.md`](docs/PLANO_LIVE_API.md).

> Já tem um `local_config.yaml` de antes? Ele não traz a seção `voice` nova — o app usa valores
> padrão mesmo assim, mas para editar os knobs apague `python/local_config.yaml` (ele é recriado)
> ou copie a seção `voice:` do `config.yaml`.

**Dependências extras na placa (Debian):** o `sounddevice` precisa do PortAudio
(`sudo apt install libportaudio2`). Para TTS offline: `pip install piper-tts` e aponte
`voice.tts.piper_model` para um `.onnx` de voz PT-BR (aí `voice.tts.engine: piper`).

---

## 🙂 O rosto (hardware)

O rosto é um **ELEGOO MAX7219 Dot Matrix Module V02** (painel de LED **8×8**), dirigido pelo
**MCU (STM32U585)** via **SPI** — pinos `VCC`, `GND`, `DIN`, `CS`, `CLK` (o `DOUT` é só para
encadear vários módulos; com um só, fica livre). O catálogo de expressões vive em
[`python/clippy/expressions.py`](python/clippy/expressions.py) e é a **fonte única** dos nomes: a
tabela de bitmaps 8×8 do sketch do MCU vai usar exatamente esses nomes.

**Fiação, firmware e voltagem:** veja [`docs/HARDWARE.md`](docs/HARDWARE.md). O sketch do MCU já
está em [`arduino/clippy_face/clippy_face.ino`](arduino/clippy_face/clippy_face.ino).

Microfone e alto-falante são **USB**, enxergados pelo **Debian do MPU** — a pipeline de áudio
roda toda no MPU.

---

## 🧩 Organização do código (pontos de extensão)

| Arquivo | Papel |
|---|---|
| `clippy/live.py` | **Modo principal:** conversa por voz em tempo real (Gemini Live API) |
| `clippy/brain.py` | Modo texto: Gemini + busca + carinha por tag `[[face:...]]` |
| `clippy/face.py` | Mostra a expressão (terminal agora → `MatrixFaceDisplay` no MAX7219) |
| `clippy/expressions.py` | Catálogo fixo de carinhas (espelhado nos bitmaps do MCU) |
| `clippy/session.py`, `io_channel.py` | Loop e I/O do modo texto |

---

## 🗺️ Roadmap

1. **Base:** conversa por texto com o Gemini + escolha de expressão. ✅
2. **Voz em tempo real:** Gemini Live API (áudio↔áudio, busca, carinha via `set_face`). ✅
3. **Wake word + estados:** palavra "clippy", máquina de estados, timer de 30 s, botão no MCU
   (abrir/fechar a sessão Live).
4. **Rosto:** sketch do MCU dirigindo o MAX7219 8×8 via Arduino Router Bridge (`MatrixFaceDisplay`).
5. **Polimento:** LEDs/matriz da placa, latência, ajuste da persona/voz.
