import serial
import time

# Substitua pela porta COM correspondente ao seu Bluetooth emparelhado
porta_bluetooth = "COM4"  # No Linux/Mac pode ser algo como '/dev/rfcomm0'

try:
    # Inicializa a conexão serial com o Bluetooth
    # O baudrate padrão para Bluetooth Serial costuma ser 9600 ou 115200 (aqui usamos 9600 para estabilidade)
    esp32 = serial.Serial(porta_bluetooth, 9600, timeout=1)
    print(f"Conectado com sucesso ao ESP32 na porta {porta_bluetooth}!")
    time.sleep(2)  # Aguarda a estabilização da conexão

    while True:
        comando = input("Digite 1 para ligar, 0 para desligar (ou 'sair'): ")

        if comando.lower() == 'sair':
            break

        if comando in ['0', '1']:
            # Envia o dado convertido em bytes (.encode())
            esp32.write(comando.encode())
            print(f"Sinal '{comando}' enviado.")
        else:
            print("Comando inválido!")

    esp32.close()
    print("Conexão encerrada.")

except Exception as e:
    print(f"Erro ao conectar ou enviar dados: {e}")
