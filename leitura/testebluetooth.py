"""
Teste rápido do link Bluetooth com o ESP32 (receptor do Lito).

Envia '1' para ligar o LED do ESP32 e '0' para desligar. Serve só para
verificar se o pareamento/porta COM estão funcionando — não usa câmera
nem o MediaPipe.

Uso:
    python leitura/testebluetooth.py

Ctrl+C encerra o programa sem traceback e sem deixar a porta COM presa.
"""

import sys
import time

try:
    import serial
except ImportError:
    print("pyserial não instalado. Instale com: pip install pyserial")
    sys.exit(1)

# Substitua pela porta COM correspondente ao seu Bluetooth emparelhado
porta_bluetooth = "COM4"  # No Linux/Mac pode ser algo como '/dev/rfcomm0'

# O Bluetooth Serial (SPP) ignora o baudrate: o valor só precisa ser aceito
# pelo driver da porta COM virtual do Windows.
esp32 = None
encerrado = False

try:
    # O "with" garante que a porta é fechada mesmo em caso de erro/Ctrl+C.
    with serial.Serial(porta_bluetooth, 9600, timeout=1) as esp32:
        print(f"Conectado com sucesso ao ESP32 na porta {porta_bluetooth}!")
        time.sleep(2)  # Aguarda a estabilização da conexão

        while True:
            try:
                comando = input("Digite 1 para ligar, 0 para desligar (ou 'sair'): ")
            except (EOFError, KeyboardInterrupt):
                print()  # nova linha depois do ^C
                break

            if comando.strip().lower() == "sair":
                break

            comando = comando.strip()
            if comando in ("0", "1"):
                # Envia o dado convertido em bytes (.encode())
                esp32.write(comando.encode())
                print(f"Sinal '{comando}' enviado.")
            else:
                print("Comando inválido!")

        encerrado = True

except KeyboardInterrupt:
    # Ctrl+C durante a abertura da porta ou uma escrita
    print("\nInterrompido pelo usuário. Conexão encerrada.")
    encerrado = True
except Exception as e:
    print(f"Erro ao conectar ou enviar dados: {e}")
finally:
    if encerrado:
        print("Conexão encerrada.")
