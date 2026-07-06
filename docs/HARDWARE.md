# Hardware do rosto — MAX7219 8×8 no Arduino UNO Q

Guia de fiação e firmware do rosto do Clippy: um painel **ELEGOO MAX7219 Dot Matrix Module V02**
(LED 8×8) dirigido pelo **MCU (STM32U585)** via SPI. O Python (MPU) escolhe a expressão e manda o
**nome** pela **Arduino Router Bridge**; o sketch guarda os bitmaps e desenha na matriz.

---

## ⚡ Precisa de código Arduino?

**Sim.** A matriz é controlada pelo MCU — o Python sozinho não fala com ela. Você grava **uma
vez** o sketch [`arduino/clippy_face/clippy_face.ino`](../arduino/clippy_face/clippy_face.ino) no
MCU (pelo Arduino IDE) e, dali em diante, o lado Python só chama:

```python
Bridge.call("set_face", "feliz")   # qualquer valor de clippy/expressions.py
Bridge.call("clippy_ping")         # -> 1 se o sketch está carregado
```

---

## 🔌 Fiação (1 módulo, o recomendado)

O Uno Q trabalha em **3.3V** (os pinos são 5V-tolerantes na entrada, mas a saída HIGH é 3.3V).
Para o MAX7219 reconhecer o nível lógico **dentro da especificação sem level shifter**, alimente
o módulo pelo pino **3V3** (não pelo 5V). Com um único módulo mostrando um rostinho, o consumo é
baixo e o 3V3 dá conta.

Conecte no **lado de ENTRADA** do módulo (o que tem **DIN**; o lado **DOUT** é só para encadear
mais módulos e fica livre aqui):

| MAX7219 (lado entrada) | Pino do UNO Q | Função |
| --- | --- | --- |
| **VCC** | **3V3** | Alimentação 3.3V (mantém a lógica na spec) |
| **GND** | **GND** | Terra comum |
| **DIN** | **D11** | Dados (MOSI) |
| **CS**  | **D10** | Latch/carga (SS) |
| **CLK** | **D13** | Clock (SCK) |

> Dica: se a carinha aparecer **de cabeça para baixo ou espelhada**, não mexa na fiação — ajuste
> `FLIP_ROWS` / `MIRROR_COLS` no topo do `.ino` e regrave.

### Quer brilho máximo? (opcional)

Se achar a matriz fraca, ou se um dia encadear vários módulos, aí sim alimente **VCC → 5V** e
coloque um **level shifter 3.3V→5V** nas linhas **DIN, CS, CLK** (ex.: shield de level shift para
Uno Q). Não ligue o 5V direto na matriz esperando lógica confiável a 3.3V — o limiar HIGH do
MAX7219 a 5V é ~3.5V, acima do que o Uno Q entrega.

---

## 🧰 Gravar o firmware (uma vez)

1. No PC, abra o **Arduino IDE** e selecione a placa **Arduino UNO Q** (MCU).
2. Instale as bibliotecas pelo **Library Manager**:
   - **LedControl** (by Eberhard Fahle) — driver do MAX7219.
   - **Arduino_RouterBridge** — RPC MessagePack MPU⇄MCU.
3. Abra `arduino/clippy_face/clippy_face.ino` e faça o **upload** para o MCU.
4. No Linux da placa, garanta o router ativo:
   ```bash
   sudo systemctl start arduino-router
   sudo systemctl enable arduino-router
   ```
5. Teste da placa (Python):
   ```python
   from arduino.app_utils import Bridge
   Bridge.call("set_face", "feliz")     # a carinha deve mudar
   print(Bridge.call("clippy_ping"))    # -> 1
   ```

---

## 🐍 Ligando no lado Python

O catálogo de expressões é [`python/clippy/expressions.py`](../python/clippy/expressions.py) — os
nomes ali (`feliz`, `triste`, `pensativo`, …) são **os mesmos** da tabela `FACES[]` no `.ino`.
Quando for plugar a matriz de verdade (fase do rosto), o [`python/clippy/face.py`](../python/clippy/face.py)
já traz a implementação `MatrixFaceDisplay`, que só chama a Bridge:

```python
class MatrixFaceDisplay:
    def __init__(self):
        from arduino.app_utils import Bridge   # existe só no runtime do App Lab na placa
        self._Bridge = Bridge
    def set_expression(self, expression):
        self._Bridge.call("set_face", expression.value)
```

Na Fase 1 usamos `TextFaceDisplay` (imprime a carinha no terminal). Trocar para o hardware é só
passar `MatrixFaceDisplay()` no lugar — o resto (`brain`, `session`) não muda.

> ⚠️ Ao adicionar/renomear uma expressão em `expressions.py`, adicione o bitmap correspondente em
> `FACES[]` no `.ino` com **o mesmo nome**. Nomes desconhecidos caem no rosto `neutro`.
