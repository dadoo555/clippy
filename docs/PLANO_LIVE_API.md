# Plano — Modo tempo-real (Gemini Live API) e comparação de áudio

Documento de planejamento. Compara as três formas de tratar áudio no Clippy e descreve **como**
implementar o modo B (Live API, áudio↔áudio streaming) **se/quando** valer a pena. Hoje o projeto
usa o modo **A** (áudio gravado → Gemini → `{texto, expressão, heard}` → TTS local).

---

## As três opções

| | **A — Áudio→Gemini + TTS local** (atual) | **B — Live API (áudio↔áudio)** | **C — Whisper local + TTS** |
|---|---|---|---|
| Como fala vira texto | Gemini entende o áudio gravado | streaming nativo, sem "texto" no meio | faster-whisper na placa |
| Como responde | edge-tts / Piper | **voz nativa do Gemini** | edge-tts / Piper |
| Latência sentida | média (grava→envia→TTS) | **baixa** (streaming, interrupções) | média |
| Funciona offline? | não (Gemini online) | não | **STT sim**; só Gemini/TTS-edge online |
| Custo de API | baixo–médio | **mais alto** (áudio in **e** out) | **mais baixo** (só texto pro Gemini) |
| Carga na placa (CPU) | leve | leve | **pesada** (Whisper na CPU ARM) |
| A carinha do Gemini | **nativa** (JSON `{expression}`) | via **function calling** (`set_face`) | nativa (JSON) |
| Complexidade de código | baixa | **alta** (async, WebSocket) | baixa |
| Maturidade do modelo | estável | **preview** | estável |

**Resumo:** A é o equilíbrio atual (bom entendimento, carinha fácil, código simples). C é o mais
barato/offline no STT, mas puxa a CPU. B é a experiência mais natural ("ele fala de volta"), mas é
mais caro, em preview, e complica a carinha e a arquitetura.

---

## O que é a Live API (tecnicamente)

- Conexão **WebSocket bidirecional** via `client.aio.live.connect()` (assíncrono).
- Modelo de áudio nativo, ex.: **`gemini-2.5-flash-preview-native-audio-dialog`**.
- Você **envia** chunks de áudio do mic (PCM 16 kHz) com `session.send_realtime_input(...)` e
  **recebe** áudio de resposta (PCM 24 kHz) em streaming, para tocar na hora.
- **VAD e interrupções embutidos**: dá pra falar por cima que ele para. Opcional "affective
  dialog" (adapta o tom à sua emoção, precisa `v1alpha`).
- Transcrições automáticas de entrada/saída disponíveis no stream (dá pra mostrar na tela).
- Docs: https://ai.google.dev/gemini-api/docs/live-api e .../live-api/get-started-sdk

---

## Mudanças de arquitetura para o B

O ponto forte do projeto — os `Protocol`s (`IOChannel`, `Brain`, `FaceDisplay`) — assume o ciclo
**turno a turno** (recebe entrada → responde). O Live API é **streaming contínuo**, então não
encaixa direto no `ConversationSession` atual. O plano:

1. **Novo módulo `live_session.py`** (assíncrono) — não reusa `session.py`. Roda um loop `asyncio`
   com duas tarefas: (a) capturar mic → `send_realtime_input`; (b) receber áudio → tocar.
2. **Mic/alto-falante em streaming**: `sounddevice` com callback (não o "grava-depois-processa"
   de hoje). Fila de chunks para enviar; buffer de reprodução para o áudio recebido.
3. **Carinha via function calling**: declarar uma tool `set_face(expression: str)` na config da
   sessão; a persona instrui o Gemini a chamá-la ao mudar de humor. No handler da tool,
   `FaceDisplay.set_expression(...)` (reusa `expressions.py` e o `MatrixFaceDisplay`).
   Assim a carinha continua **escolhida pelo Gemini**, só que por chamada de função em vez de JSON.
4. **CLI**: novo subcomando `python -m clippy live` (mantém `chat`/`chat --voice` como estão).
5. **Persona/estado**: o `system_instruction` continua igual; o timer de 30 s e a wake word
   (Fase 3) passam a controlar **abrir/fechar a sessão Live** em vez do loop de turnos.
6. **Dependências**: nenhuma nova além do `google-genai` já instalado (a Live API vem nele). Some
   a necessidade de faster-whisper e edge-tts **neste modo**.

### Esboço (ilustrativo, não é o código final)

```python
import asyncio
from google import genai
from google.genai import types

client = genai.Client(api_key=...)
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=PERSONA,
    tools=[{"function_declarations": [SET_FACE_DECL]}],
)

async def run():
    async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
        async def mic_to_gemini(): ...   # sounddevice callback -> session.send_realtime_input
        async def gemini_to_speaker():   # async for msg in session.receive():
            # msg.data -> tocar; msg.tool_call -> set_face(...); msg.server_content -> transcrição
            ...
        await asyncio.gather(mic_to_gemini(), gemini_to_speaker())
```

---

## Custos (ordem de grandeza — confirme em https://ai.google.dev/pricing)

Regra útil: **áudio conta ~32 tokens por segundo**. Uma fala de 4 s ≈ **~128 tokens** de entrada.

- **C (Whisper local):** o Gemini recebe só **texto** (~20–40 tokens/turno). É o **mais barato**
  em API. O "custo" é CPU da placa + baixar o modelo Whisper.
- **A (áudio→Gemini):** o Gemini recebe **~128 tokens de áudio/turno** em vez de ~30 de texto. Na
  prática, no `flash`, a diferença por turno é **pequena em valor absoluto** — A é barato. O TTS
  (edge/Piper) não custa API.
- **B (Live API):** paga **áudio de entrada _e_ áudio de saída nativo**, em streaming contínuo
  (inclui silêncios da conversa). A saída em áudio nativo é a parte cara. Estimativa grosseira:
  **várias vezes** o custo de A por conversa, além de ser **preview** (preço/limite sujeitos a
  mudança) e ter tier grátis mais restrito.

**Ranking de custo de API:** C < A < B. **Ranking de CPU na placa:** A ≈ B (leves) < C (Whisper).

---

## Recomendação

Ficar no **A** para as Fases 3–4 (wake word, estados, rosto). O A dá bom entendimento de fala,
mantém a carinha nativa e o código simples, e o custo é modesto. Deixar o **B** como um
**experimento à parte** (`python -m clippy live`) para depois que o resto estiver redondo — é
quando o "ele responde falando em tempo real" compensa a complexidade extra.

**Gatilhos para migrar ao B:**
- A latência do A (gravar → enviar → TTS) incomodar na conversa.
- Quiser interrupções naturais (falar por cima).
- O tier/custo do Live API estiver confortável para o uso.

Ao migrar, o `set_face` por function calling é a peça central a validar primeiro (garante que a
carinha continua decidida pelo Gemini).
