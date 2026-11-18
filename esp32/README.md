# ESP32 — receptor Bluetooth do Lito

Sketch Arduino (`esp32.ino`) que roda no **ESP32-WROOM-32** e faz o receptor de comandos
do drone. Ele abre um **Bluetooth Serial** com o nome **"LITO"** e, a cada gesto confirmado
pelo Python (`leitura/leitura_mão.py`), recebe **1 byte (uma letra)** e aciona os motores
ou o LED de feedback. O controle é **on/off** (HIGH = ligado, LOW = desligado), **sem PWM**.

## Pinos

| Função | GPIO | Observação |
|:--|:--:|:--|
| Motor 1 — Frente Direita (FD) | 25 | Gate de MOSFET IRLB4132 |
| Motor 2 — Trás Direita (TD) | 26 | Gate de MOSFET IRLB4132 |
| Motor 3 — Trás Esquerda (TE) | 33 | Gate de MOSFET IRLB4132 |
| Motor 4 — Frente Esquerda (FE) | 32 | Gate de MOSFET IRLB4132 |
| LED de feedback | 2 | Pisca 60 ms ao receber comando |

## Comandos

| Letra | Gesto | Motores acionados |
|:--:|:--|:--|
| `E` | ESQUERDA | TE + FE |
| `D` | DIREITA | FD + TD |
| `F` | FRENTE | FD + FE |
| `T` | TRÁS | TD + TE |
| `C` | CIMA | todos (FD + TD + TE + FE) |
| `B` | BAIXO | nenhum (todos desligados) |
| `1` / `0` | teste | apenas o LED (não mexe nos motores) |

## Segurança e como carregar

- ⚠️ **Teste SEM hélices.** Motores ficam em **LOW no boot** (antes de qualquer outra coisa).
- **Failsafe:** sem nenhum byte por **2000 ms**, todos os motores são desligados.
- Compilar/carregar: abra `esp32/esp32.ino` na **IDE Arduino** (core ESP32 instalado,
  placa **"ESP32 Dev Module"**) ou rode
  `arduino-cli compile --fqbn esp32:esp32:esp32 esp32`.
- Monitor Serial em **115200** baud (USB, só para depuração). A conexão **Bluetooth
  Serial (SPP)** não usa baudrate — o Python no PC abre a porta COM em `9600` e o
  firmware apenas chama `ESP_BT.begin("LITO")`.
