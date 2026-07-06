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

## 🏃 Rodar

```bash
python -m clippy chat            # conversa real com o Gemini (precisa da GEMINI_API_KEY)
python -m clippy chat --dry-run  # modo offline: ecoa a entrada sem chave nem internet
```

Exemplo de sessão:

```
você > Oi, quem é você?
[carinha: feliz]
clippy > Oi! Eu sou o Clippy, seu ajudante animado. Como posso te ajudar hoje?
```

Digite `sair` (ou `Ctrl-D`) para encerrar. Na primeira execução, `python/local_config.yaml` é
criado a partir de `python/config.yaml` — edite o **local** para ajustar modelo e persona.

---

## 🎤 Falar e ouvir (Fase 2 — voz)

Mesma conversa, mas por **microfone e alto-falante**. Você fala, o Clippy transcreve (Whisper),
pensa (Gemini) e responde **em voz alta** (TTS). A transcrição também aparece na tela.

```bash
python -m clippy devices            # lista mic/alto-falante (para escolher no config, se precisar)
python -m clippy chat --voice       # conversa por voz com o Gemini
python -m clippy chat --voice --dry-run  # testa só o áudio (mic->Whisper->eco->voz), sem Gemini
```

Como funciona:
- **Entrada (aperta-e-fala):** aperte **ENTER**, fale, e aperte **ENTER de novo para parar** — você
  controla o fim, então não corta a frase no meio. Também dá pra **digitar** em vez de falar
  (fallback, e para `sair`). Duas formas de virar texto (`voice.stt_engine`):
  - `gemini` (padrão): manda o **áudio direto pro Gemini** (sem Whisper, sem baixar modelo).
  - `whisper`: transcreve **local/offline** com faster-whisper e mostra `você (voz) > ...` na tela
    (bom para a placa, para `--dry-run` e para ver o que foi entendido).
- **Saída:** **edge-tts** (voz PT-BR online, padrão) ou **Piper** (offline, para a placa).
- **Memória:** o Clippy lembra da conversa **durante a sessão** e **zera quando você reinicia**.
- **Busca na internet:** ligada (`gemini.web_search`) — clima, notícias e fatos vêm do Google
  Search em vez de serem inventados.

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

| Arquivo | Papel | Vira, nas próximas fases |
|---|---|---|
| `clippy/brain.py` | Gemini + saída estruturada `{texto, expressão}` | — |
| `clippy/io_channel.py` | Entrada/fala em texto | ✅ `voice_channel.py` (Whisper + TTS) já existe |
| `clippy/face.py` | Mostra a expressão (terminal agora) | `MatrixFaceDisplay` (MAX7219 via Bridge) |
| `clippy/session.py` | O loop de conversa | Máquina de estados + timer de 30 s |
| `clippy/expressions.py` | Catálogo fixo de carinhas | Espelhado nos bitmaps do MCU |

Cada subsistema é um `Protocol` (mesmo molde do projeto irmão `taubeerkennung`), então as versões
de voz e de hardware encaixam sem tocar no resto.

---

## 🗺️ Roadmap

1. **Base:** loop de conversa por texto com o Gemini + escolha de expressão. ✅
2. **Voz:** faster-whisper na entrada, TTS (edge-tts/Piper) na saída, VAD por energia. ✅
3. **Wake word + estados:** Porcupine ("clippy"), máquina de estados, timer de 30 s, botão
   liga/desliga no MCU.
4. **Rosto:** sketch do MCU dirigindo o MAX7219 8×8 via Arduino Router Bridge.
5. **Polimento:** LEDs/matriz da placa, latência, ajuste da persona.
