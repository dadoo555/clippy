# Clippy — Assistente de Voz para o Arduino UNO Q

O **Clippy** é um assistente animado e bem-humorado que roda **inteiramente no Arduino UNO Q**.
A meta final: ele ouve a palavra **"clippy"**, você fala, a fala vai pro **Gemini**, e ele
responde **por voz** — com um **rosto de LED** (matriz MAX7219 8×8) que reage ao que está sendo
dito. A expressão da carinha é escolhida pelo **próprio Gemini** a cada resposta.

Hoje o Clippy já **conversa por voz em tempo real** (Gemini Live API): dorme ouvindo a palavra
**"clippy"**, acorda, conversa por áudio (com busca na internet e carinha escolhida pelo Gemini) e
**volta a dormir após 10 s** de silêncio. Falta a matriz de LED física (o sketch já existe) e o
botão do MCU.

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

Como funciona:
- **Dorme ouvindo "clippy"** (Vosk, local, offline — não gasta API). Ao ouvir, acorda e conecta.
- **Áudio↔áudio streaming** via `client.aio.live.connect()` (mic a 16 kHz → Gemini → voz a 24 kHz).
- **Volta a dormir após 10 s de silêncio** (`live.inactivity_timeout_s`).
- **Busca na internet** (`gemini.web_search`) — clima/notícias/fatos reais, não inventados.
- **Carinha decidida pelo Gemini** pela função `set_face`; hoje imprime no terminal, e vira o
  MAX7219 pela Bridge na fase do rosto.
- `Ctrl-C` sai. Sem wake word configurada, roda uma sessão direta e encerra no timeout.

### Wake word "clippy" (Vosk)

Precisa de um modelo Vosk pequeno (offline, uma vez):
1. Baixe um modelo pequeno em https://alphacephei.com/vosk/models — ex.: **`vosk-model-small-pt-0.3`**
   (PT, ~50 MB). Descompacte.
2. Aponte a **pasta** em `config.yaml` → `wake.model_path: "C:/.../vosk-model-small-pt-0.3"`.
3. Rode `python -m clippy live`. Se `wake.model_path` ficar vazio, o wake word fica desligado e ele
   entra direto numa sessão.

O Vosk transcreve por cima e casa qualquer palavra da lista `wake.phrases` (padrão: `clip, clipe,
clipi, clippy, clique`) — ajuste se ele acordar de menos/demais.

### Onde ficam as instruções do modelo (persona)

Em `config.yaml` → `gemini.persona`. Esse texto é o **system prompt** e vale para os dois modos
(`live` e `chat`). É lá que você define personalidade, idioma e estilo.

Outros ajustes (`config.yaml`): `live.model`/`voice`/`inactivity_timeout_s`, `gemini.web_search`,
`live.input_device`/`output_device`. Se `live.model` der erro para sua chave, troque-o (o comentário
no config lista alternativas).

> ⚠️ **Apagou o `local_config.yaml`?** Ótimo — ele se recria a partir de `config.yaml` no próximo
> run, já com as seções `live` e `wake`.

## 💬 Rodar por texto (opcional, para testar)

```bash
python -m clippy chat            # conversa por texto com o Gemini (precisa da chave)
python -m clippy chat --dry-run  # offline: ecoa a entrada, sem chave nem internet
```

Útil para validar chave/persona sem áudio. Digite `sair` (ou `Ctrl-D`) para encerrar.

**Dependência extra na placa (Debian):** o `sounddevice` precisa do PortAudio
(`sudo apt install libportaudio2`).

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
| `clippy/live.py` | **Modo principal:** voz em tempo real + máquina de estados (dorme/acorda/timeout) |
| `clippy/wake.py` | Wake word "clippy" offline (Vosk) |
| `clippy/brain.py` | Modo texto: Gemini + busca + carinha por tag `[[face:...]]` |
| `clippy/face.py` | Mostra a expressão (terminal agora → `MatrixFaceDisplay` no MAX7219) |
| `clippy/expressions.py` | Catálogo fixo de carinhas (espelhado nos bitmaps do MCU) |
| `clippy/session.py`, `io_channel.py` | Loop e I/O do modo texto |

---

## 🗺️ Roadmap

1. **Base:** conversa por texto com o Gemini + escolha de expressão. ✅
2. **Voz em tempo real:** Gemini Live API (áudio↔áudio, busca, carinha via `set_face`). ✅
3. **Wake word + estados:** palavra "clippy" (Vosk), dorme/acorda, timeout de 10 s. ✅
   Falta o **botão físico** do MCU (liga/desliga).
4. **Rosto:** sketch do MCU dirigindo o MAX7219 8×8 via Arduino Router Bridge (`MatrixFaceDisplay`).
5. **Polimento:** LEDs/matriz da placa, latência, ajuste da persona/voz.
