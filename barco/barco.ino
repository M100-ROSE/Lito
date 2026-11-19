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
// DUAS ORIGENS aceitas, com a MESMA lógica (processarComando):
//   1) Bluetooth Classic/SPP (ESP_BT) - nome "BARCO", uso no drone;
//   2) Serial USB (Serial)            - o mesmo cabo de dados do upload.
//      Serve para TESTAR SEM BLUETOOTH: `python leitura_mao_barco.py
//      --porta COMx`. Nesse modo FECHE o Monitor Serial, senão a porta
//      fica ocupada (o Windows não a abre duas vezes) e o texto digitado
//      no monitor vira comando.
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
// BLUETOOTH (mesmo esquema do esp32/esp32.ino, que funciona no PC):
//  - Só `BluetoothSerial ESP_BT;` e um `ESP_BT.begin("BARCO")` no setup.
//    Sem checar retorno, sem retry, sem ESP_BT.end() e sem
//    esp_bt_gap_set_scan_mode().
//  - ÚNICA exceção, opcional e controlada por LIMPAR_PAREAMENTOS (veja
//    abaixo): apagar os bonds salvos UMA vez, logo depois do begin().
//  - No loop, `ESP_BT.hasClient()` é apenas LIDO (sem alterar a lógica) para
//    imprimir uma vez por transição "Cliente Bluetooth CONECTADO /
//    DESCONECTADO". Serve para separar "link caiu" de "placa reiniciou".
//  - Todo diagnóstico extra de rádio foi REMOVIDO DE PROPÓSITO: em um PC o
//    anúncio do "BARCO" não aparecia, enquanto o "LITO" (que só chama
//    begin()) aparecia. Ficamos exatamente com o caminho já provado.
//  - O que ainda é impresso é só texto no Serial USB; nenhuma chamada de
//    rádio a mais. Se o problema for emparelhamento, veja o README >
//    "Se o BARCO não aparecer no Bluetooth".
//
// LIMPAR_PAREAMENTOS (pareamento "pela metade"):
//  - Quando o Windows emparelha pela metade (bond criado no PC mas não no
//    ESP32, ou bond velho/corrompido no ESP32), o aparelho aparece na lista
//    como "Não conectado" e nunca conecta -- e o Windows não deixa parear de
//    novo porque acha que já está pareado.
//  - Com LIMPAR_PAREAMENTOS = 1, o ESP32 APAGA TODOS os bonds salvos nele no
//    boot, forçando um pareamento limpo do zero no PC (é preciso parear de
//    novo). Tem que ser chamado DEPOIS do begin(): a API de bond só funciona
//    com o Bluetooth já iniciado.
//  - Com LIMPAR_PAREAMENTOS = 0, nada é apagado (comportamento anterior).
//  - É só para teste: depois de pareado e funcionando, volte para 0 para não
//    apagar o pareamento bom a cada boot.
// ------------------------------------------------------------------

// Apaga TODOS os pareamentos salvos no ESP32 no boot (útil no teste:
// garante que o PC faça um pareamento limpo). 1 = apaga, 0 = mantém.
#define LIMPAR_PAREAMENTOS 1

#include "BluetoothSerial.h" // Biblioteca padrão do ESP32 (Bluetooth Classic/SPP)
#include "esp_system.h"      // esp_reset_reason(): motivo do último reset

// O core 3.3.11 marca BluetoothSerial como [[deprecated]] (só porque sairá
// do build padrão na 4.0.0). Este #pragma é APENAS cosmético: não altera o
// anúncio nem o comportamento do rádio — serve só para o build ficar com
// zero avisos. Nenhuma chamada de rádio extra existe aqui.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
BluetoothSerial ESP_BT; // mesmo objeto simples do esp32/esp32.ino
#pragma GCC diagnostic pop

// --- Pinos ---
const int PINO_SAIDA = 25; // HIGH = duas mãos abertas
const int LED = 2;         // feedback; strapping pin (use resistor para GND)

// Tempo do pulso curto no LED ao receber um comando novo (ms)
const int BLINK_MS = 60;

// Tempo máximo (ms) sem comando válido (de qualquer origem: BT ou USB)
// antes do failsafe
const unsigned long FAILSAFE_MS = 2000;

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

// Último estado lido de ESP_BT.hasClient(), só para imprimir UMA vez por
// transição (observabilidade: descobrir se o link cai ou a placa reinicia).
// começa em false porque o ESP_BT ainda nem foi iniciado no boot.
bool clienteBtAnterior = false;

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
// LÓGICA ÚNICA do protocolo. É chamada tanto pelo Bluetooth quanto pelo
// Serial USB, então o comportamento é idêntico nas duas origens.
// `origem` só aparece nas mensagens do Serial (nunca muda a decisão).
// ------------------------------------------------------------------
void processarComando(char sinalRecebido, const char *origem) {
  // Byte desconhecido ('\n', '\r', texto digitado no Monitor Serial...):
  // IGNORA. Não renova o failsafe (lixo não pode manter o pino 25 ligado),
  // não vira ultimoComando (não pode "comer" o próximo 'A') e não bloqueia
  // os demais bytes da rajada. Avisa uma vez por byte distinto.
  if (sinalRecebido != 'A' && sinalRecebido != 'F') {
    if (sinalRecebido != ultimoByteIgnorado) {
      ultimoByteIgnorado = sinalRecebido;
      Serial.print("Byte ignorado em ");
      Serial.print(origem);
      Serial.println(" (comando deve ser 'A' ou 'F').");
    }
    return;
  }

  // Comando válido: a partir daqui ele renova o failsafe
  ultimoByteMs = millis();
  ultimoByteIgnorado = 0; // permite avisar de novo um lixo futuro

  // Comando repetido (o Python reenvia a cada ~0,5 s): já está aplicado,
  // então só renova o failsafe — sem Serial e sem LED.
  if (sinalRecebido == ultimoComando) {
    return;
  }
  ultimoComando = sinalRecebido;

  Serial.print("Sinal recebido em ");
  Serial.print(origem);
  Serial.print(": ");
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

// ------------------------------------------------------------------
// Consome TUDO que estiver disponível em UMA fonte (Bluetooth ou Serial
// USB) e entrega byte a byte para processarComando().
// ------------------------------------------------------------------
void processarFonte(Stream &fonte, const char *origem) {
  while (fonte.available()) {
    // read() devolve int (-1 = nada); compara como int para não depender
    // da signedness de char em bytes >= 0x80.
    int lido = fonte.read();
    if (lido < 0) {
      break; // nada mais para ler
    }
    processarComando((char)lido, origem);
  }
}

// ------------------------------------------------------------------
// Traduz o motivo do último reset (esp_reset_reason()) para texto.
// Serve só para o Monitor Serial: nada de rádio, nada de lógica.
// ------------------------------------------------------------------
const char *nomeMotivoReset(esp_reset_reason_t motivo) {
  switch (motivo) {
    case ESP_RST_POWERON:  return "POWERON";
    case ESP_RST_EXT:      return "EXT";
    case ESP_RST_SW:       return "SW";
    case ESP_RST_PANIC:    return "PANIC";
    case ESP_RST_INT_WDT:  return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT:      return "WDT";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_SDIO:     return "SDIO";
    default:               return "DESCONHECIDO";
  }
}

// ------------------------------------------------------------------
// Bloco de diagnóstico de boot. Se estas linhas NÃO aparecerem no
// Monitor Serial (115200), o problema é cabo/porta/gravação — não é
// Bluetooth. Serve também para ver qual firmware está realmente rodando.
// Sem chamadas de rádio: só texto.
// ------------------------------------------------------------------
void imprimirDiagnostico() {
  Serial.println();
  Serial.println("=== BARCO: firmware de teste (pino 25) ===");
  Serial.print("Core Arduino-ESP32: ");
  Serial.println(ESP.getCoreVersion());
  Serial.print("Chip: ");
  Serial.println(ESP.getChipModel());

  // Motivo do último reset: se esta linha reaparecer a cada queda, a placa
  // está REINICIANDO (BROWNOUT = alimentação fraca), não é o Windows
  // derrubando o SPP ocioso.
  esp_reset_reason_t motivoReset = esp_reset_reason();
  Serial.print("Reset anterior: ");
  Serial.print(nomeMotivoReset(motivoReset));
  Serial.print(" (");
  Serial.print((int)motivoReset);
  Serial.println(")");

  // Tempo ligado (millis do boot): se for sempre um valor pequeno, confirma
  // que é reboot e não uma simples desconexão de Bluetooth.
  Serial.print("Tempo ligado no boot: ");
  Serial.print(millis());
  Serial.println(" ms");

  Serial.println("==========================================");
}

void setup() {
  // 1) SEGURANÇA: saída em LOW o quanto antes, antes de qualquer coisa
  pinMode(PINO_SAIDA, OUTPUT);
  definirSaida(false);

  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);

  Serial.begin(115200);

  // 2) Texto de boot (só Serial, nada de rádio): prova qual firmware roda
  imprimirDiagnostico();

  // 3) Bluetooth EXATAMENTE como no esp32/esp32.ino que funciona:
  //    só o begin(), com nome próprio para não colidir com o "LITO".
  ESP_BT.begin("BARCO");

  // 3.1) Opcional (LIMPAR_PAREAMENTOS): apaga os bonds antigos UMA vez.
  //      DEPOIS do begin() de propósito: a API de bond do ESP32 só funciona
  //      com o Bluetooth já iniciado. Sem isso, um pareamento "pela metade"
  //      no Windows (aparelho listado como "Não conectado") nunca reconecta.
  if (LIMPAR_PAREAMENTOS) {
    ESP_BT.deleteAllBondedDevices();
    Serial.println("Pareamentos antigos apagados (faca o pareamento de novo no PC).");
  }

  Serial.println("BARCO pronto para emparelhar.");
  Serial.println("Teste: 'A' = duas maos abertas (pino 25 HIGH).");

  // 4) O Serial USB também aceita 'A'/'F' (mesma lógica): plano B de teste.
  Serial.println("Controle por USB (Serial) tambem ativo: A/F.");
  Serial.println("  -> Para usar o USB, FECHE o Monitor Serial (a porta e uma so).");

  ultimoByteMs = millis(); // o failsafe começa a contar daqui
}

void loop() {
  // --- Observabilidade: mudanças de conexão Bluetooth (só leitura) ---
  // Imprime UMA vez por transição. Não altera nada do protocolo/failsafe.
  bool clienteBtAgora = ESP_BT.hasClient();
  if (clienteBtAgora != clienteBtAnterior) {
    clienteBtAnterior = clienteBtAgora;
    if (clienteBtAgora) {
      Serial.println("Cliente Bluetooth CONECTADO");
    } else {
      Serial.println("Cliente Bluetooth DESCONECTADO");
    }
  }

  // --- Comandos: as DUAS origens usam a MESMA lógica ---
  // Bluetooth primeiro, depois Serial USB. Nenhuma das duas bloqueia.
  processarFonte(ESP_BT, "Bluetooth");
  processarFonte(Serial, "USB");

  // --- Failsafe: sem comando válido por FAILSAFE_MS -> desliga a saída ---
  // Feito com millis(), sem delay() extra. Age uma vez por ausência de
  // sinal (definirSaida(false) zera saidaLigada), sem inundar o Serial.
  if (saidaLigada && (millis() - ultimoByteMs >= FAILSAFE_MS)) {
    definirSaida(false);
    // esquece o último comando: se o mesmo estado chegar de novo (ex.:
    // PC voltou de uma suspensão), ele precisa religar a saída
    ultimoComando = 0;
    Serial.println("FAILSAFE: sem comando (BT/USB), pino 25 DESLIGADO.");
  }

  // --- Blink não bloqueante do LED (nada de delay()) ---
  if (ledPendente && (long)(millis() - ledApagarEm) >= 0) {
    digitalWrite(LED, LOW);
    ledPendente = false;
  }

  delay(20); // loop rápido: comandos chegam sem atraso perceptível
}
