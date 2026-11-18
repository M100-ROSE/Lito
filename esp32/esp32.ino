// ------------------------------------------------------------------
// Lito - ESP32 (receptor de comandos por gestos via Bluetooth Serial)
//
// O Python (leitura/leitura_mao.py) envia UMA letra por mudança de
// direção confirmada:
//   'T' -> TRÁS      'F' -> FRENTE
//   'E' -> ESQUERDA  'D' -> DIREITA
//   'C' -> CIMA      'B' -> BAIXO
// Mantemos também os comandos antigos      '1' -> LED liga
// criados para o testebluetooth.py:        '0' -> LED desliga
//
// --------------------------------------------------------------
// MODO DE TESTE (on/off) DOS 4 MOTORES
// --------------------------------------------------------------
// Esta versão aciona os motores de forma binária (HIGH = ligado,
// LOW = desligado), SEM PWM. Cada GPIO vai no Gate de um MOSFET
// IRLB4132 (com pull-down de 10 kΩ no Gate), então:
//
//   Motor 1 (Frente Direita)  -> GPIO 25  (MOTOR_FD)
//   Motor 2 (Trás Direita)    -> GPIO 26  (MOTOR_TD)
//   Motor 3 (Trás Esquerda)   -> GPIO 33  (MOTOR_TE)
//   Motor 4 (Frente Esquerda) -> GPIO 32  (MOTOR_FE)
//   LED de feedback           -> GPIO 2   (LED)
//
// Mapeamento gesto -> motores ligados:
//   'E' ESQUERDA -> TE + FE  (motores da esquerda)
//   'D' DIREITA  -> FD + TD  (motores da direita)
//   'F' FRENTE   -> FD + FE  (motores da frente)
//   'T' TRÁS     -> TD + TE  (motores de trás)
//   'C' CIMA     -> todos os 4 motores
//   'B' BAIXO    -> nenhum motor (todos desligados)
//   '1' / '0'    -> apenas o LED do pino 2 (não mexem nos motores)
//
// SEGURANÇA:
//  - No setup() todos os motores são colocados em LOW ANTES de tudo,
//    para nunca iniciar com motor ligado.
//  - FAILSAFE: se passar mais de FAILSAFE_MS (2000 ms) sem receber
//    NENHUM byte pelo Bluetooth, todos os motores são desligados.
//    Assim, se o PC cair / o sinal sumir, o drone não fica com motor
//    ligado sozinho.
//
// O loop continua com delay(20) e esvazia TODOS os bytes disponíveis
// por passo, para não atrasar os comandos.
// ------------------------------------------------------------------

#include "BluetoothSerial.h" // Biblioteca padrão do ESP32

BluetoothSerial ESP_BT;

// --- Pinos ---
const int LED = 2;

// Motores (Gate dos MOSFETs IRLB4132): HIGH = ligado, LOW = desligado
const int MOTOR_FD = 25; // Motor 1 - Frente Direita
const int MOTOR_TD = 26; // Motor 2 - Trás Direita
const int MOTOR_TE = 33; // Motor 3 - Trás Esquerda
const int MOTOR_FE = 32; // Motor 4 - Frente Esquerda

// Tempo do pulso curto no LED ao receber uma letra de direção (ms)
const int BLINK_MS = 60;

// Tempo máximo (ms) sem nenhum byte do Bluetooth antes do failsafe
const unsigned long FAILSAFE_MS = 2000;

// Instante (millis) do último byte recebido pelo Bluetooth
unsigned long ultimoByteMs = 0;

// Guarda se algum motor está ligado, para o failsafe saber se precisa agir
bool motoresLigados = false;

// ------------------------------------------------------------------
// Aciona os 4 motores de uma vez.
// true = liga (HIGH) / false = desliga (LOW).
// Toda mudança de motor passa por aqui, evitando repetir digitalWrite
// em cada case do switch.
// ------------------------------------------------------------------
void ligarMotores(bool fd, bool td, bool te, bool fe) {
  digitalWrite(MOTOR_FD, fd ? HIGH : LOW);
  digitalWrite(MOTOR_TD, td ? HIGH : LOW);
  digitalWrite(MOTOR_TE, te ? HIGH : LOW);
  digitalWrite(MOTOR_FE, fe ? HIGH : LOW);

  motoresLigados = (fd || td || te || fe);
}

// Desliga todos os motores (usado no setup, no 'B' e no failsafe)
void pararMotores() {
  ligarMotores(false, false, false, false);
}

// Pisca rápido o LED uma vez, para dar feedback visível do comando
// recebido. Termina com o LED apagado (pulso curto, não trava o loop).
void blinkRapido() {
  digitalWrite(LED, HIGH);
  delay(BLINK_MS);
  digitalWrite(LED, LOW);
}

void setup() {
  // 1) SEGURANÇA: motores em LOW o quanto antes, antes de qualquer coisa
  pinMode(MOTOR_FD, OUTPUT);
  pinMode(MOTOR_TD, OUTPUT);
  pinMode(MOTOR_TE, OUTPUT);
  pinMode(MOTOR_FE, OUTPUT);
  pararMotores();

  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);

  Serial.begin(115200);
  ESP_BT.begin("LITO"); // O nome do dispositivo continua "LITO"

  ultimoByteMs = millis(); // começa a contar o failsafe a partir daqui
  Serial.println("O dispositivo já pode ser emparelhado!");
  Serial.println("Modo de teste: motores on/off (teste SEM hélices!).");
}

void loop() {
  // Processa TODOS os bytes disponíveis neste passo do loop
  while (ESP_BT.available()) {
    char sinalRecebido = ESP_BT.read(); // Lê o caractere enviado
    ultimoByteMs = millis();            // qualquer byte reinicia o failsafe

    Serial.print("Sinal recebido: ");
    Serial.println(sinalRecebido);

    switch (sinalRecebido) {
      // --- comandos de direção enviados pelo leitura_mao.py ---
      case 'T': // TRÁS: motores de trás
        ligarMotores(false, true, true, false);
        Serial.println("TRÁS -> motores TD + TE");
        blinkRapido();
        break;
      case 'F': // FRENTE: motores da frente
        ligarMotores(true, false, false, true);
        Serial.println("FRENTE -> motores FD + FE");
        blinkRapido();
        break;
      case 'E': // ESQUERDA: motores da esquerda
        ligarMotores(false, false, true, true);
        Serial.println("ESQUERDA -> motores TE + FE");
        blinkRapido();
        break;
      case 'D': // DIREITA: motores da direita
        ligarMotores(true, true, false, false);
        Serial.println("DIREITA -> motores FD + TD");
        blinkRapido();
        break;
      case 'C': // CIMA: todos os motores
        ligarMotores(true, true, true, true);
        Serial.println("CIMA -> todos os motores (FD + TD + TE + FE)");
        blinkRapido();
        break;
      case 'B': // BAIXO: desliga todos
        pararMotores();
        Serial.println("BAIXO -> motores desligados");
        blinkRapido();
        break;

      // --- comandos antigos de teste do LED (testebluetooth.py) ---
      // Não alteram o estado dos motores: controlam só o LED do pino 2.
      case '1':
        digitalWrite(LED, HIGH);
        Serial.println("LED ligado (motores não foram alterados)");
        break;
      case '0':
        digitalWrite(LED, LOW);
        Serial.println("LED desligado (motores não foram alterados)");
        break;

      default:
        // Byte desconhecido: só avisa e segue o loop
        Serial.println("Comando não reconhecido.");
        break;
    }
  }

  // --- Failsafe: sem nenhum byte por FAILSAFE_MS -> desliga os motores ---
  // Feito com millis(), sem delay() extra. Só age uma vez por ausência de
  // sinal (pararMotores() zera motoresLigados), para não inundar o Serial.
  if (motoresLigados && (millis() - ultimoByteMs >= FAILSAFE_MS)) {
    pararMotores();
    Serial.println("FAILSAFE: sem sinal Bluetooth, motores desligados.");
  }

  delay(20); // loop rápido: comandos chegam sem atraso perceptível
}
