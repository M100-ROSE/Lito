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
| Failsafe | 2 s sem nenhum byte → pino 25 desliga |

Mão "aberta" = pelo menos **4 dos 5** dedos esticados (`MIN_DEDOS_ABERTOS`).
O estado só é enviado após votação (4 de 5 leituras) e a mesma letra é
reenviada a cada 0,5 s.

## Como rodar

```powershell
pip install -r ../requirements.txt   # já cobre mediapipe, opencv e pyserial
python leitura_mao_barco.py
```

Teclas `s` ou `q` encerram. O modelo é usado de `../leitura/hand_landmarker.task`.

## Firmware

Abra `barco.ino` na Arduino IDE e grave com a placa ESP32.
O dispositivo Bluetooth aparece como **"BARCO"** (não "LITO").
Ajuste `PORTA_BLUETOOTH = "COM4"` no Python para o COM que aparecer no
Gerenciador de Dispositivos.

## Avisos

- Sem Bluetooth (pyserial ausente ou porta errada) o script roda só com a
  câmera e avisa uma vez — não trava.
- Sem bytes por 2 s o firmware desliga o pino 25 sozinho (failsafe).
- Isto é só liga/desliga: não há controle de velocidade/PWM.
