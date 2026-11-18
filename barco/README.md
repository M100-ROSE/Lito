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

## Como rodar

```powershell
pip install -r ../requirements.txt   # já cobre mediapipe, opencv e pyserial
python leitura_mao_barco.py
```

Teclas `s` ou `q` encerram. O modelo é usado de `../leitura/hand_landmarker.task`.

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
Gerenciador de Dispositivos.

### Monitor Serial (115200)

No boot o sketch imprime um bloco de diagnóstico antes de iniciar o rádio:

```text
=== BARCO: diagnostico de boot ===
Core Arduino-ESP32: 3.3.11
ESP-IDF: v5.5.x
Chip: ESP32-D0WD-V3 rev 3, nucleos: 2
MAC Bluetooth: AA:BB:CC:DD:EE:FF
Heap livre no boot: 123456 bytes
=================================
Iniciando Bluetooth Serial como "BARCO"... OK.
Modo de varredura: CONECTAVEL + DESCOBRIVEL (o PC deve listar "BARCO").
Dispositivos pareados (bonded): 0
BARCO pronto para emparelhar.
Teste: 'A' = duas maos abertas (pino 25 HIGH).
```

Depois disso, cada transição de conexão aparece **uma vez**:
`Cliente Bluetooth CONECTADO.` / `Cliente Bluetooth DESCONECTADO.`
(é só observabilidade; o failsafe de 2 s não depende disso).

Se `ESP_BT.begin()` falhar, o Serial mostra:

```text
Iniciando Bluetooth Serial como "BARCO"... FALHOU (ESP_BT.begin() retornou false).
  -> Nova tentativa em 3 s. Se repetir, veja README > 'Se o BARCO nao aparecer no Bluetooth'.
```

e o firmware tenta de novo a cada 3 s, sem travar o loop.

## Se o BARCO não aparecer no Bluetooth

Siga na ordem — cada passo elimina uma causa:

1. **Confirme que o sketch FOI GRAVADO (não só compilado).**
   Na Arduino IDE: placa **ESP32 Dev Module**, porta **COM** correta em
   *Ferramentas > Porta*, e clique em **Upload**. Tem que terminar com
   `Hash of data verified` / `Hard resetting via RTS pin` e **sem erro**.
   Compilar (✓) não grava nada.
2. **Abra o Monitor Serial em 115200** logo depois do upload.
   Você deve ver o bloco `=== BARCO: diagnostico de boot ===` e
   `BARCO pronto para emparelhar.`
   - **Se não aparecer NADA no Monitor**, o problema é cabo/porta/gravação:
     não é Bluetooth. Vá para o passo 3.
   - Se aparecer `FALHOU`, copie a mensagem exata (passo 7).
3. **Use cabo USB com dados.** Cabo só de carga não aparece como porta COM
   e não grava. Prefira uma **porta USB direta do PC**, não hub; troque de
   cabo antes de suspeitar da placa.
4. **Confira a versão do firmware pelo nome.** No Windows, *Configurações >
   Bluetooth e dispositivos > Adicionar dispositivo > Bluetooth*:
   - `BARCO` só aparece enquanto o firmware está anunciando;
   - se aparecer **`LITO`**, ainda está gravado o firmware do drone —
     regrave o `barco.ino` (passo 1);
   - no Windows 11 o dispositivo novo pode cair em **"Outros
     dispositivos"** em vez da lista principal.
5. **Placa reiniciando em loop (brownout).** Se o bloco de diagnóstico
   repetir sem parar no Monitor, é alimentação: use uma porta/USB que
   aguente o pico do rádio, tire carga do **GPIO 25** e confira se o LED no
   **GPIO 2** está para o GND **por resistor** (curto no GPIO 2 derruba o
   boot).
6. **Versão do chip.** Bluetooth Classic (SPP) só existe no **ESP32
   clássico** (DevKit/WROOM-32). ESP32-**S2/S3/C3/C6** têm apenas BLE e
   **nunca** vão anunciar "BARCO" via `BluetoothSerial`.
7. **`begin` falhando.** Se o Monitor mostrar `FALHOU` repetidamente,
   registre a mensagem exata e o valor de `Heap livre no boot`. Reinicie a
   placa com o botão **EN**; se persistir, regrave com *Erase All Flash
   Before Sketch Upload* habilitado.

## Avisos

- Sem Bluetooth (pyserial ausente ou porta errada) o script roda só com a
  câmera e avisa uma vez — não trava.
- Sem comandos válidos por 2 s o firmware desliga o pino 25 sozinho
  (failsafe). Bytes desconhecidos, como `\n`/`\r`, são ignorados e não
  renovam esse relógio.
- Isto é só liga/desliga: não há controle de velocidade/PWM.
