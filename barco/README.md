# Barco — teste isolado "duas mãos abertas"

Teste **separado do drone** (não mexe em `leitura/` nem em `esp32/`).
O Python lê a webcam, e se detectar **exatamente 2 mãos, ambas abertas**,
liga o **pino 25** do ESP32. Qualquer outro caso desliga.

## Pinos e protocolo

| Item | Valor |
| --- | --- |
| Saída | GPIO 25 (HIGH = ligado, LOW = desligado) — **sem PWM** |
| LED de feedback | GPIO 2 (strapping pin: LED ao GND por resistor) |
| `'A'` | duas mãos abertas → pino 25 LIGADO |
| `'F'` | 0/1 mão ou alguma fechada → pino 25 DESLIGADO |
| Failsafe | 2 s sem comando válido (`'A'`/`'F'`) → pino 25 desliga |

Mão "aberta" = pelo menos **4 dos 5** dedos esticados (`MIN_DEDOS_ABERTOS`).
O estado só é enviado após votação (4 de 5 leituras) e a mesma letra é
reenviada a cada 0,5 s.

Os comandos são aceitos por **duas origens**, com a mesma lógica no firmware:
**Bluetooth** (`BARCO`) e **Serial USB** (`--porta COMx`).

## Como rodar

```powershell
pip install -r ../requirements.txt   # já cobre mediapipe, opencv e pyserial
python leitura_mao_barco.py                  # Bluetooth (PORTA_BLUETOOTH, COM4)
python leitura_mao_barco.py --porta COM5     # USB do ESP32 (cabo de dados)
python leitura_mao_barco.py --listar         # só lista as portas COM e sai
```

Teclas `s` ou `q` encerram. O modelo é usado de `../leitura/hand_landmarker.task`.
No HUD aparece `PORT: COM5` (link aberto) ou `PORT: sem link` (nada é enviado).

## Teste sem Bluetooth (pelo USB)

O mesmo cabo USB que grava o sketch também leva os comandos: o firmware escuta
`'A'`/`'F'` no **Serial USB** além do Bluetooth, com a mesma lógica. Dá para
validar todo o resto (MediaPipe, votação, pino 25, failsafe) sem emparelhar nada.

1. **Grave** `barco.ino` (Upload, placa ESP32 Dev Module).
2. **Feche o Monitor Serial** da Arduino IDE. A porta COM é exclusiva: com o
   monitor aberto o Python não consegue abrir a porta — e o que você digitar no
   monitor vira comando para o firmware.
3. **Descubra a COM do USB**: Gerenciador de Dispositivos → *Portas (COM e LPT)*
   → `Silicon Labs CP210x` / `CH340` (é a do USB, **não** a "Standard Serial
   over Bluetooth link"). Ou rode:
   ```powershell
   python leitura_mao_barco.py --listar
   ```
4. **Rode apontando para essa porta**:
   ```powershell
   python leitura_mao_barco.py --porta COM5
   ```
   No modo USB o script abre a porta em **115200** (o mesmo baud do
   `Serial.begin` do sketch). Se precisar forçar outro: `--baud 115200`.
5. **O que deve acontecer**: com **2 mãos abertas** o pino 25 liga (`PIN 25:
   LIGADO`) e a janela `estado` mostra `baixo.jpg`; em qualquer outro caso ele
   desliga (`PIN 25: DESLIGADO`) e aparece `esquerda.jpg`. O HUD mostra
   `PORT: COM5`.

Diferenças em relação ao Bluetooth: o alcance é o comprimento do cabo (não serve
para o drone voando), mas a lógica testada é exatamente a mesma — só muda o
caminho até o ESP32. Um aviso no Monitor Serial, no boot, confirma o modo:
`Controle por USB (Serial) tambem ativo: A/F.`

## Imagem de referência

Além da janela do vídeo, uma janela separada chamada **`estado`** (à direita
do vídeo) mostra a imagem do estado **confirmado**, de `../leitura/direcoes/`:
`baixo.jpg` quando o estado é `'A'` (pino 25 **LIGADO**) e `esquerda.jpg`
quando é `'F'` (pino 25 **DESLIGADO**). Se a imagem faltar, o script só avisa
e continua; fechar a janela no "X" não derruba nem reabre nada.

## Firmware

Abra `barco.ino` na Arduino IDE e grave com a placa ESP32.
O dispositivo Bluetooth aparece como **"BARCO"** (não "LITO").
Ajuste `PORTA_BLUETOOTH = "COM4"` no Python para o COM que aparecer no
Gerenciador de Dispositivos. Para o caminho USB veja
**Teste sem Bluetooth (pelo USB)** acima.

### Monitor Serial (115200)

No boot o sketch imprime poucas linhas de texto (nenhuma chamada de rádio além
do próprio `ESP_BT.begin()`):

```text
=== BARCO: firmware de teste (pino 25) ===
Core Arduino-ESP32: 3.3.11
Chip: ESP32-D0WD-V3
==========================================
BARCO pronto para emparelhar.
Teste: 'A' = duas maos abertas (pino 25 HIGH).
Controle por USB (Serial) tambem ativo: A/F.
  -> Para usar o USB, FECHE o Monitor Serial (a porta e uma so).
```

O Bluetooth aqui é **o mesmo esquema simples do `esp32/esp32.ino`** (que
funciona): só `BluetoothSerial ESP_BT;` e `ESP_BT.begin("BARCO")`. Não há retry,
não há `ESP_BT.end()`, não há `esp_bt_gap_set_scan_mode()`, não há consulta de
bonded e não há detecção de conexão (`hasClient()`) no loop. Qualquer
diagnóstico extra de rádio foi removido de propósito: em um PC o anúncio do
"BARCO" não aparecia, e o "LITO" — que só chama `begin()` — aparecia.

## Se o BARCO não aparecer no Bluetooth

Siga na ordem — cada passo elimina uma causa:

1. **Confirme que o sketch FOI GRAVADO (não só compilado).**
   Na Arduino IDE: placa **ESP32 Dev Module**, porta **COM** correta em
   *Ferramentas > Porta*, e clique em **Upload**. Tem que terminar com
   `Hash of data verified` / `Hard resetting via RTS pin` e **sem erro**.
   Compilar (✓) não grava nada.
2. **Abra o Monitor Serial em 115200** logo depois do upload.
   Você deve ver `BARCO pronto para emparelhar.`
   - **Se não aparecer NADA no Monitor**, o problema é cabo/porta/gravação:
     não é Bluetooth. Vá para o passo 3.
3. **Use cabo USB com dados.** Cabo só de carga não aparece como porta COM
   e não grava. Prefira uma **porta USB direta do PC**, não hub; troque de
   cabo antes de suspeitar da placa.
4. **Adicione o dispositivo pelo Windows.** *Configurações > Bluetooth e
   dispositivos > Adicionar dispositivo > Bluetooth*:
   - `BARCO` só aparece enquanto o firmware está anunciando;
   - se aparecer **`LITO`**, ainda está gravado o firmware do drone —
     regrave o `barco.ino` (passo 1);
   - no **Windows 11 24H2/25H2** a lista principal esconde classes
     incomuns (SPP/serial): clique em **"Mostrar todos os dispositivos"** e,
     se existir, ponha a descoberta em **Avançado**. O aparelho pode cair em
     **"Outros dispositivos"** em vez da lista principal.
   - **Remova pareamentos antigos** antes de tentar de novo: apague `BARCO`
     em *Configurações > Bluetooth e dispositivos*, e confira também em
     `control printers` (Win+R) se sobrou alguma porta "Standard Serial over
     Bluetooth link" apontando para ele.
5. **Prove que o rádio do PC tem Bluetooth Classic.** Emparelhe um **fone
   Bluetooth** comum no mesmo PC. Se o fone também não aparecer, o problema
   é do adaptador/driver do Windows, não do ESP32 (há PCs só com BLE).
6. **Placa reiniciando em loop (brownout).** Se as linhas de boot repetirem
   sem parar no Monitor, é alimentação: use uma porta/USB que aguente o pico
   do rádio, tire carga do **GPIO 25** e confira se o LED no **GPIO 2** está
   para o GND **por resistor** (curto no GPIO 2 derruba o boot).
7. **Versão do chip.** Bluetooth Classic (SPP) só existe no **ESP32
   clássico** (DevKit/WROOM-32). ESP32-**S2/S3/C3/C6** têm apenas BLE e
   **nunca** vão anunciar "BARCO" via `BluetoothSerial`.
8. **Plano B: modo USB.** Se nada disso resolver, valide tudo pelo cabo:
   `python leitura_mao_barco.py --porta COMx` (veja **Teste sem Bluetooth
   (pelo USB)** acima). Se o USB funciona e o Bluetooth não, o firmware está
   certo — o problema está no anúncio/emparelhamento do PC, não na lógica.

## Avisos

- Sem link (pyserial ausente, porta errada, ou Monitor Serial aberto no modo
  USB) o script roda só com a câmera e avisa uma vez — não trava.
- Sem comandos válidos por 2 s o firmware desliga o pino 25 sozinho
  (failsafe), valendo para as duas origens (Bluetooth e USB). Bytes
  desconhecidos, como `\n`/`\r`, são ignorados e não renovam esse relógio.
- Isto é só liga/desliga: não há controle de velocidade/PWM.
