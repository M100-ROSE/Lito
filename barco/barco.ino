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
//  - FAILSAFE: se passar FAILSAFE_MS (2000 ms) sem nenhum COMANDO VÁLIDO
//    ('A' ou 'F'), o pino 25 volta para LOW e um aviso é impresso UMA vez.
//    Byte desconhecido (ex.: '\n', '\r', lixo do terminal) é IGNORADO: não
//    renova o failsafe, não vira ultimoComando e não bloqueia o próximo
//    comando válido. Assim lixo não mantém a saída ligada.
//  - O LED é não bloqueante (ledApagarEm + ledPendente + millis()), sem
//    delay() no processamento; o único delay é o 20 ms do fim do loop.
//
// DIAGNÓSTICO (para "não aparece no Bluetooth do PC"):
//  - Logo no boot imprime core, ESP-IDF, chip/revisão/núcleos, MAC
//    Bluetooth (esp_read_mac) e heap livre. Serve para PROVAR que este
//    firmware está rodando (e não o "LITO" antigo nem um sketch vazio).
//  - Checa o retorno de ESP_BT.begin("BARCO") (é bool). Se falhar, avisa
//    no Serial e TENTA DE NOVO a cada 3 s, sem travar o loop.
//  - Reforça o modo de varredura (conectável + descobrível) e imprime o
//    resultado. O nome "BARCO" é aplicado pelo próprio begin(); o core
//    3.3.11 NÃO tem setDeviceName() nem setDiscoverable(), por isso o
//    equivalente real é esp_bt_gap_set_scan_mode() (API do ESP-IDF).
//  - Detecta e imprime UMA vez cada transição de conexão (hasClient()).
//    Isso é só observabilidade: o failsafe NÃO depende de hasClient().
// ------------------------------------------------------------------

#include "BluetoothSerial.h" // Biblioteca padrão do ESP32 (Bluetooth Classic/SPP)
#include "esp_gap_bt_api.h"  // esp_bt_gap_set_scan_mode(): modo descobrível
#include "esp_mac.h"         // esp_read_mac() + ESP_MAC_BT

// BluetoothSerial está marcada como [[deprecated]] no core 3.3.11 apenas
// porque será removida do build padrão na 4.0.0 — Bluetooth Classic/SPP
// continua suportado nesta versão. Silenciamos só ESTE aviso (a linha
// abaixo) para manter o build limpo; o resto dos avisos segue ativo.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
BluetoothSerial ESP_BT;
#pragma GCC diagnostic pop

// --- Pinos ---
const int PINO_SAIDA = 25; // HIGH = duas mãos abertas
const int LED = 2;         // feedback; strapping pin (use resistor para GND)

// Tempo do pulso curto no LED ao receber um comando novo (ms)
const int BLINK_MS = 60;

// Tempo máximo (ms) sem comando válido do Bluetooth antes do failsafe
const unsigned long FAILSAFE_MS = 2000;

// Intervalo entre novas tentativas de ESP_BT.begin() quando ele falha (ms)
const unsigned long BT_RETRY_MS = 3000;

// Instante (millis) do último COMANDO VÁLIDO recebido
unsigned long ultimoByteMs = 0;

// Instante (millis) em que o pulso do LED deve apagar
unsigned long ledApagarEm = 0;

// Há pulso de LED pendente? (flag separada: não usa 0 como sentinela,
// que quebraria se millis() + BLINK_MS caísse exatamente em 0)
bool ledPendente = false;

// Último comando VÁLIDO processado. Repetido = idempotente e silencioso.
char ultimoComando = 0;

// Último byte desconhecido avisado, para não inundar o Serial quando o
// mesmo lixo (ex.: "\n\n\n") chega repetido.
char ultimoByteIgnorado = 0;

// Estado atual da saída (para o failsafe saber se precisa agir)
bool saidaLigada = false;

// --- Diagnóstico de Bluetooth (não interfere no protocolo) ---
bool btPronto = false;                    // begin() retornou true
unsigned long proximaTentativaBtMs = 0;   // quando tentar begin() de novo
bool clienteConectado = false;            // estado anterior de hasClient()

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
  ledPendente = true;
}

// ------------------------------------------------------------------
// Bloco de diagnóstico de boot. Se estas linhas NÃO aparecerem no
// Monitor Serial (115200), o problema é cabo/porta/gravação — não é
// Bluetooth. Serve também para ver qual firmware está realmente rodando.
// ------------------------------------------------------------------
void imprimirDiagnostico() {
  uint8_t mac[6] = {0, 0, 0, 0, 0, 0};
  esp_read_mac(mac, ESP_MAC_BT); // MAC do controlador Bluetooth clássico

  Serial.println();
  Serial.println("=== BARCO: diagnostico de boot ===");
  Serial.print("Core Arduino-ESP32: ");
  Serial.println(ESP.getCoreVersion());
  Serial.print("ESP-IDF: ");
  Serial.println(ESP.getSdkVersion());
  Serial.print("Chip: ");
  Serial.print(ESP.getChipModel());
  Serial.print(" rev ");
  Serial.print(ESP.getChipRevision());
  Serial.print(", nucleos: ");
  Serial.println(ESP.getChipCores());
  Serial.printf(
    "MAC Bluetooth: %02X:%02X:%02X:%02X:%02X:%02X\n", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
  );
  Serial.print("Heap livre no boot: ");
  Serial.print(ESP.getFreeHeap());
  Serial.println(" bytes");
  Serial.println("=================================");
}

// ------------------------------------------------------------------
// Inicia o Bluetooth e REPORTA o resultado. begin() é bool: se falhar,
// apenas agenda nova tentativa (sem travar) e explica no Serial.
// ------------------------------------------------------------------
void iniciarBluetooth() {
  Serial.print("Iniciando Bluetooth Serial como \"BARCO\"... ");
  bool ok = ESP_BT.begin("BARCO"); // nome próprio: não conflita com "LITO"

  if (!ok) {
    Serial.println("FALHOU (ESP_BT.begin() retornou false).");
    Serial.println("  -> Nova tentativa em 3 s. Se repetir, veja README > 'Se o BARCO nao aparecer no Bluetooth'.");
    proximaTentativaBtMs = millis() + BT_RETRY_MS;
    return;
  }

  btPronto = true;
  Serial.println("OK.");

  // O core 3.3.11 não expõe setDiscoverable(). O BluetoothSerial já liga
  // o modo descobrível no ESP_SPP_INIT_EVT; reforçamos com a API real do
  // ESP-IDF para garantir que o PC consiga listar "BARCO".
  esp_err_t err = esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
  if (err == ESP_OK) {
    Serial.println("Modo de varredura: CONECTAVEL + DESCOBRIVEL (o PC deve listar \"BARCO\").");
  } else {
    Serial.print("AVISO: esp_bt_gap_set_scan_mode falhou, codigo ");
    Serial.println((int)err);
  }

  // Estado de emparelhamento (bonded). getNumberOfBondedDevices() existe
  // no core 3.3.11 e é só uma consulta, não bloqueia.
  Serial.print("Dispositivos pareados (bonded): ");
  Serial.println(ESP_BT.getNumberOfBondedDevices());

  Serial.println("BARCO pronto para emparelhar.");
  Serial.println("Teste: 'A' = duas maos abertas (pino 25 HIGH).");
}

void setup() {
  // 1) SEGURANÇA: saída em LOW o quanto antes, antes de qualquer coisa
  pinMode(PINO_SAIDA, OUTPUT);
  definirSaida(false);

  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);

  Serial.begin(115200);

  // 2) Diagnóstico: prova qual firmware está rodando e em qual placa
  imprimirDiagnostico();

  // 3) Bluetooth com retorno checado
  iniciarBluetooth();

  ultimoByteMs = millis(); // o failsafe começa a contar daqui
}

void loop() {
  // --- Bluetooth: se begin() falhou, tenta de novo sem travar o loop ---
  if (!btPronto && (long)(millis() - proximaTentativaBtMs) >= 0) {
    ESP_BT.end(); // limpa estado parcial antes de tentar de novo
    iniciarBluetooth();
  }

  // --- Transições de conexão: imprime UMA vez por mudança ---
  // Apenas observabilidade. O failsafe abaixo continua independente de
  // hasClient(): é decisão consciente não bloquear a saída por conexão.
  bool conectadoAgora = btPronto && ESP_BT.hasClient();
  if (conectadoAgora != clienteConectado) {
    clienteConectado = conectadoAgora;
    if (conectadoAgora) {
      Serial.println("Cliente Bluetooth CONECTADO.");
    } else {
      Serial.println("Cliente Bluetooth DESCONECTADO.");
    }
  }

  // Processa TODOS os bytes disponíveis neste passo
  while (ESP_BT.available()) {
    // read() devolve int (-1 = nada); compara como int para não depender
    // da signedness de char em bytes >= 0x80.
    int lido = ESP_BT.read();
    if (lido < 0) {
      break; // nada mais para ler
    }
    char sinalRecebido = (char)lido;

    // Byte desconhecido ('\n', '\r', lixo do terminal...): IGNORA.
    // Não renova o failsafe (lixo não pode manter o pino 25 ligado),
    // não vira ultimoComando (não pode "comer" o próximo 'A') e não
    // bloqueia os demais bytes da rajada. Avisa uma vez por byte distinto.
    if (sinalRecebido != 'A' && sinalRecebido != 'F') {
      if (sinalRecebido != ultimoByteIgnorado) {
        ultimoByteIgnorado = sinalRecebido;
        Serial.println("Byte ignorado (comando deve ser 'A' ou 'F').");
      }
      continue; // volta ao while: outros bytes da rajada seguem sendo lidos
    }

    // Comando válido: a partir daqui ele renova o failsafe
    ultimoByteMs = millis();
    ultimoByteIgnorado = 0; // permite avisar de novo um lixo futuro

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
    }
  }

  // --- Failsafe: sem comando válido por FAILSAFE_MS -> desliga a saída ---
  // Feito com millis(), sem delay() extra. Age uma vez por ausência de
  // sinal (definirSaida(false) zera saidaLigada), sem inundar o Serial.
  if (saidaLigada && (millis() - ultimoByteMs >= FAILSAFE_MS)) {
    definirSaida(false);
    // esquece o último comando: se o mesmo estado chegar de novo (ex.:
    // PC voltou de uma suspensão), ele precisa religar a saída
    ultimoComando = 0;
    Serial.println("FAILSAFE: sem comando Bluetooth, pino 25 DESLIGADO.");
  }

  // --- Blink não bloqueante do LED (nada de delay()) ---
  if (ledPendente && (long)(millis() - ledApagarEm) >= 0) {
    digitalWrite(LED, LOW);
    ledPendente = false;
  }

  delay(20); // loop rápido: comandos chegam sem atraso perceptível
}
