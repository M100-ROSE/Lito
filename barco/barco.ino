// ------------------------------------------------------------------
// BARCO - teste isolado: "as duas mãos estão abertas?" -> pino 25
//
// Este sketch NÃO é o drone. É um receptor Bluetooth Serial separado,
// com nome de dispositivo "BARCO" (para não conflitar com o "LITO"),
// pensado para um teste simples de saída liga/desliga.
//
// Protocolo (1 byte por mensagem, enviado por barco/leitura_mao_barco.py):
//   'A' -> as DUAS mãos estão abertas  => pino 25 = HIGH (LIGADO)
//   'F' -> qualquer outro caso         => pino 25 = LOW  (DESLIGADO)
//
// O Python REENVIA a mesma letra a cada ~0,5 s enquanto o estado não
// muda. Comando repetido é IDEMPOTENTE e SILENCIOSO aqui: só renova o
// relógio do failsafe, sem reimprimir no Serial e sem piscar o LED.
//
// Pinos:
//   GPIO 25 -> saída do teste (HIGH = ligado). NÃO há PWM: é só
//              liga/desliga. Se for acionar algo indutivo, use um driver
//              adequado (MOSFET/relé) e pull-down no gate/base.
//   GPIO 2  -> LED de feedback (pisca curto ao mudar de estado).
//              GPIO2 é strapping pin do ESP32: ligue o LED ao GND por um
//              resistor (ex.: 220 Ω-1 kΩ), NUNCA direto no 3V3.
//
// SEGURANÇA:
//  - No topo do setup() o pino 25 vai para LOW ANTES de tudo, para nunca
//    iniciar ligado.
//  - FAILSAFE: se passar FAILSAFE_MS (2000 ms) sem NENHUM byte, o pino 25
//    volta para LOW e um aviso é impresso UMA vez.
//  - O LED é não bloqueante (ledApagarEm + millis()), sem delay() no
//    processamento; o único delay é o 20 ms do fim do loop.
// ------------------------------------------------------------------

#include "BluetoothSerial.h" // Biblioteca padrão do ESP32

BluetoothSerial ESP_BT;

// --- Pinos ---
const int PINO_SAIDA = 25; // HIGH = duas mãos abertas
const int LED = 2;         // feedback; strapping pin (use resistor para GND)

// Tempo do pulso curto no LED ao receber um comando novo (ms)
const int BLINK_MS = 60;

// Tempo máximo (ms) sem nenhum byte do Bluetooth antes do failsafe
const unsigned long FAILSAFE_MS = 2000;

// Instante (millis) do último byte recebido
unsigned long ultimoByteMs = 0;

// Instante (millis) em que o pulso do LED deve apagar (0 = nada pendente)
unsigned long ledApagarEm = 0;

// Último comando processado. Repetido = idempotente e silencioso.
char ultimoComando = 0;

// Estado atual da saída (para o failsafe saber se precisa agir)
bool saidaLigada = false;

// ------------------------------------------------------------------
// Aplica o estado da saída. Toda mudança passa por aqui.
// ------------------------------------------------------------------
void definirSaida(bool ligada) {
  digitalWrite(PINO_SAIDA, ligada ? HIGH : LOW);
  saidaLigada = ligada;
}

// ------------------------------------------------------------------
// Pisca o LED por BLINK_MS sem bloquear: só acende e agenda o instante
// de apagar, verificado no fim do loop().
// ------------------------------------------------------------------
void blinkRapido() {
  digitalWrite(LED, HIGH);
  ledApagarEm = millis() + BLINK_MS;
}

void setup() {
  // 1) SEGURANÇA: saída em LOW o quanto antes, antes de qualquer coisa
  pinMode(PINO_SAIDA, OUTPUT);
  definirSaida(false);

  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);

  Serial.begin(115200);
  ESP_BT.begin("BARCO"); // nome próprio: não conflita com o "LITO"

  ultimoByteMs = millis(); // o failsafe começa a contar daqui
  Serial.println("BARCO pronto para emparelhar.");
  Serial.println("Teste: 'A' = duas maos abertas (pino 25 HIGH).");
}

void loop() {
  // Processa TODOS os bytes disponíveis neste passo
  while (ESP_BT.available()) {
    char sinalRecebido = ESP_BT.read();
    ultimoByteMs = millis(); // qualquer byte reinicia o failsafe

    // Comando repetido (o Python reenvia a cada ~0,5 s): já está
    // aplicado, então só renova o failsafe — sem Serial e sem LED.
    if (sinalRecebido == ultimoComando) {
      continue;
    }
    ultimoComando = sinalRecebido;

    Serial.print("Sinal recebido: ");
    Serial.println(sinalRecebido);

    switch (sinalRecebido) {
      case 'A': // duas mãos abertas
        definirSaida(true);
        Serial.println("ABERTAS -> pino 25 LIGADO");
        blinkRapido();
        break;

      case 'F': // qualquer outro caso
        definirSaida(false);
        Serial.println("FECHADAS -> pino 25 DESLIGADO");
        blinkRapido();
        break;

      default:
        // Byte desconhecido: só avisa e segue
        Serial.println("Comando nao reconhecido.");
        break;
    }
  }

  // --- Failsafe: sem nenhum byte por FAILSAFE_MS -> desliga a saída ---
  // Feito com millis(), sem delay() extra. Age uma vez por ausência de
  // sinal (definirSaida(false) zera saidaLigada), sem inundar o Serial.
  if (saidaLigada && (millis() - ultimoByteMs >= FAILSAFE_MS)) {
    definirSaida(false);
    // esquece o último comando: se o mesmo estado chegar de novo (ex.:
    // PC voltou de uma suspensão), ele precisa religar a saída
    ultimoComando = 0;
    Serial.println("FAILSAFE: sem sinal Bluetooth, pino 25 DESLIGADO.");
  }

  // --- Blink não bloqueante do LED (nada de delay()) ---
  if (ledApagarEm && (long)(millis() - ledApagarEm) >= 0) {
    digitalWrite(LED, LOW);
    ledApagarEm = 0;
  }

  delay(20); // loop rápido: comandos chegam sem atraso perceptível
}
