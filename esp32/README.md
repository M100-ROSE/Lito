# ESP32 — receptor Bluetooth do Lito

Sketch Arduino (`esp32.ino`) que roda no **ESP32-WROOM-32** e faz o receptor de comandos
do drone. Ele abre um **Bluetooth Serial** com o nome **"LITO"** e, a cada gesto confirmado
pelo Python (`leitura/leitura_mao.py`), recebe **1 byte (uma letra)** e aciona os motores
ou o LED de feedback. O controle é **on/off** (HIGH = ligado, LOW = desligado), **sem PWM**.

O Python reenvia a **mesma letra a cada ~0,5 s** enquanto o gesto continua confirmado
(contrato: continua **1 letra por mensagem**). No firmware, comando repetido é
**idempotente e silencioso**: só renova o failsafe, sem reimprimir no Serial e sem
piscar o LED de novo.

## Pinos

| Função | GPIO | Observação |
|:--|:--:|:--|
| Motor 1 — Frente Direita (FD) | 25 | Gate de MOSFET IRLB4132 |
| Motor 2 — Trás Direita (TD) | 26 | Gate de MOSFET IRLB4132 |
| Motor 3 — Trás Esquerda (TE) | 33 | Gate de MOSFET IRLB4132 |
| Motor 4 — Frente Esquerda (FE) | 32 | Gate de MOSFET IRLB4132 |
| LED de feedback | 2 | Pisca 60 ms a cada comando novo; com `'1'` fica aceso em regime |

> GPIO2 é um *strapping pin* do ESP32. Ligue o LED ao **GND através de um resistor**
> (ex.: 220 Ω–1 kΩ), nunca direto no 3V3, para não interferir no boot.

## Comandos

| Letra | Gesto | Efeito |
|:--:|:--|:--|
| `E` | ESQUERDA | motores TE + FE |
| `D` | DIREITA | motores FD + TD |
| `F` | FRENTE | motores FD + FE |
| `T` | TRÁS | motores TD + TE |
| `C` | CIMA | todos (FD + TD + TE + FE) |
| `B` | BAIXO | nenhum (todos desligados) |
| `1` | teste | **acende o LED em regime** (não mexe nos motores) |
| `0` | teste | apaga o LED (não mexe nos motores) |

O `'1'` deixa o LED **aceso fixo**, não é só um pisca. Esse estado é **sobrescrito pelo
próximo comando de direção**, que volta ao comportamento normal (pulso de 60 ms por
comando novo). Os comandos `1`/`0` não alteram o estado dos motores.

## Segurança e como carregar

- ⚠️ **Teste SEM hélices.** Motores ficam em **LOW no boot** (antes de qualquer outra coisa).
- **Failsafe:** sem nenhum byte por **2000 ms**, todos os motores são desligados. Por isso
  o Python reenvia a letra da direção atual a cada 0,5 s — sem isso, um gesto mantido por
  mais de 2 s desligaria os motores.
- Compilar/carregar: abra `esp32/esp32.ino` na **IDE Arduino** (core ESP32 instalado,
  placa **"ESP32 Dev Module"**) ou rode
  `arduino-cli compile --fqbn esp32:esp32:esp32 esp32`.
- Monitor Serial em **115200** baud (USB, só para depuração). A conexão **Bluetooth
  Serial (SPP)** não usa baudrate — o Python no PC abre a porta COM em `9600` e o
  firmware apenas chama `ESP_BT.begin("LITO")`.
