# Contexto do Projeto Lito

Drone controlado por gestos das mãos: Python/MediaPipe/OpenCV no PC lê as mãos pela
câmera e envia comandos via Bluetooth Serial para um ESP32 (sketch Arduino em
`esp32/esp32.ino`).

- Equipe: Kaike, Maria e Marcos (1ºDSB, Colégio Kennedy — feira de ciências).
- Repositório: https://github.com/M100-ROSE/Lito.git (branch `main`).

## Preferências

- Documentação e comentários em português do Brasil.
- Commits no padrão `tipo: descrição` (`feat:`, `fix:`, `docs:`, etc.).
- Nunca commitar segredos, `.env`, `__pycache__`, artefatos de build ou arquivos temporários.
- Não usar `--force`, `reset --hard` ou `clean -fd` sem autorização explícita.

## Estado atual

### O que o sistema faz hoje

1. **Detecção** — MediaPipe HandLandmarker (modo VIDEO) encontra até 2 mãos por frame.
2. **Classificação** — a função `direcao()` (pura, sem efeitos colaterais) decide o gesto
   a partir dos 5 booleanos de dedos esticados de cada mão.
3. **Votação** — `direcao_estavel()` confirma a direção apenas por voto majoritário das
   últimas leituras, eliminando flicker.
4. **Envio** — `processar_envio()` manda UMA letra ao ESP32 **quando a direção confirmada
   MUDA** (`INTERVALO_MINIMO_ENVIO = 0,5 s` entre comandos diferentes) e, enquanto o gesto
   se mantém, **REENVIA a mesma letra a cada `INTERVALO_REENVIO = 0,5 s`** — o sketch tem
   failsafe de 2 s sem bytes, então o reenvio mantém o comando vivo. O throttle guarda a
   janela e tenta de novo no frame seguinte (não descarta mais o comando novo) e a "última
   enviada" só é marcada quando `enviar_comando()` devolve sucesso; falha de escrita
   derruba o link (`esp32 = None`), avisa uma vez e o programa segue só com a câmera.

### Arquivos-chave

- `leitura/leitura_mao.py` — programa principal (câmera + gestos + envio serial).
  - Constantes no topo: `PORTA_BLUETOOTH = "COM4"`, `BAUDRATE = 9600`, `INTERVALO_MINIMO_ENVIO = 0.5`
    e `INTERVALO_REENVIO = 0.5`.
  - `main()` + `if __name__ == "__main__"`, com funções `processar_frame`, `carregar_imagens`,
    `criar_detector`, `conectar_esp32`, `exibir_captura` e `processar_envio`.
  - Caminhos das imagens (`leitura/direcoes/*.jpg`) e do modelo `hand_landmarker.task`
    resolvidos relativos à pasta do script (`PASTA_SCRIPT`, via pathlib), com avisos no
    boot se algo não carregar.
- `leitura/direcoes/*.jpg` — imagens de referência exibidas para cada direção.
- `leitura/hand_landmarker.task` — modelo do MediaPipe.
- `leitura/testebluetooth.py` — teste manual da conexão (usa os comandos `'1'`/`'0'`).
- `esp32/esp32.ino` — sketch Arduino (receptor Bluetooth Serial, nome do dispositivo "LITO"):
  loop rápido (`delay(20)`) que esvazia QUALQUER byte disponível com `while(ESP_BT.available())`,
  `switch` com letras de direção que agora **acionam os 4 motores em modo de TESTE on/off**
  (`HIGH` = ligado) pelos MOSFETs IRLB4132 — `E` → TE+FE, `D` → FD+TD, `F` → FD+FE,
  `T` → TD+TE, `C` → todos os 4, `B` → nenhum — via `ligarMotores(fd, td, te, fe)` e
  `pararMotores()`, com constantes `MOTOR_FD=25`, `MOTOR_TD=26`, `MOTOR_TE=33`,
  `MOTOR_FE=32` colocadas em `OUTPUT`/`LOW` no início do `setup()`; imprime no Serial e
  faz blink no LED do pino 2 **sem bloquear** (`ledApagarEm` + desligamento no fim do `loop()`,
  sem `delay(60)`). Comando **repetido é idempotente e silencioso** (`ultimoComando`): o
  reenvio de 0,5 s do Python só renova o failsafe, sem reimprimir no Serial nem piscar o LED.
  **Failsafe** de `FAILSAFE_MS = 2000` com `millis()`: sem nenhum byte Bluetooth por 2 s,
  desliga todos os motores e **zera `ultimoComando`** (o mesmo gesto pode religar depois).
  Para compatibilidade com `testebluetooth.py`, `'1'` deixa o LED **aceso em regime** e `'0'`
  apaga (não tocam nos motores); byte desconhecido apenas avisa. O uso de `hasClient()` foi
  avaliado e **descartado** (pode retornar `false` logo após reconectar e derrubar os motores);
  o motivo está documentado em comentário no sketch.
- `esp32/README.md` — pinos, tabela de comandos, failsafe e como compilar/carregar o sketch.
- `barco/` — **teste isolado do drone** ("as duas mãos estão abertas?"):
  - `barco/leitura_mao_barco.py` — detector standalone (HandLandmarker em modo VIDEO,
    2 mãos, suavização, votação 4 de 5). Mão "aberta" = ≥4 de 5 dedos esticados
    (`MIN_DEDOS_ABERTOS`), confiança ≥0,8; envia `'A'` só com exatamente 2 mãos e ambas
    abertas, qualquer outro caso `'F'`; reenvia a letra a cada 0,5 s (`INTERVALO_REENVIO`)
    por causa do failsafe; pyserial opcional e HUD com o estado do "PIN 25".
    Exibe também uma janela separada **`estado`** (à direita do vídeo) com a imagem do
    estado confirmado, de `leitura/direcoes/`: `baixo.jpg` quando `'A'` (pino 25 ligado)
    e `esquerda.jpg` quando `'F'` ou quando ainda não há envio confirmado (`None`);
    imagem faltando só gera aviso e fechar a janela no "X" não derruba o programa.
    Linha de comando (`argparse`): `--porta COMx` (padrão `PORTA_BLUETOOTH` = COM4),
    `--baud N` e `--listar` (usa `serial.tools.list_ports` e sai sem abrir a câmera).
    Baud automático: porta padrão 9600 (Bluetooth); qualquer outra porta 115200 (o mesmo
    do `Serial.begin` do sketch). `conectar_esp32(porta, baud)` avisa o motivo da falha
    e o HUD mostra `PORT: COMx` ou `PORT: sem link (COMx)`; sem link segue só com a câmera.
  - `barco/barco.ino` — receptor Bluetooth Serial **"BARCO"** (não conflita com o "LITO"):
    `PINO_SAIDA = 25` em LOW no topo do `setup()`, `'A'` → HIGH, `'F'` → LOW, comando
    repetido idempotente/silencioso, LED 2 não bloqueante e `FAILSAFE_MS = 2000` (zera
    `ultimoComando`). Sem PWM: é só liga/desliga.
    **Bluetooth voltou ao esquema simples do `esp32/esp32.ino`** (que funciona no PC):
    só `BluetoothSerial ESP_BT;` e `ESP_BT.begin("BARCO")` no `setup()` — sem checar
    retorno, sem retry/`ESP_BT.end()`, sem `esp_bt_gap_set_scan_mode()`, sem
    `getNumberOfBondedDevices()`, sem MAC/`esp_read_mac()` e sem `hasClient()` no loop.
    Motivo: em um PC específico o anúncio do "BARCO" não aparecia enquanto o "LITO" (que
    só chama `begin()`) aparecia; todo o diagnóstico extra de rádio foi removido de
    propósito. `imprimirDiagnostico()` ficou só com 2 linhas de texto (core + modelo do
    chip) e não faz nenhuma chamada de rádio.
    **Única exceção ao esquema mínimo**: a constante `LIMPAR_PAREAMENTOS` (topo do
    `barco.ino`) — com `1`, logo DEPOIS do `begin()` (a API de bond exige o Bluetooth já
    iniciado) o sketch chama `ESP_BT.deleteAllBondedDevices()` e avisa no Serial,
    forçando um pareamento limpo no PC; com `0`, nada é apagado (comportamento anterior).
    É uma constante **de teste**: apaga o bom pareamento a cada boot, então deve voltar
    para `0` depois de tudo funcionar.
    **Duas origens de comando**, com a MESMA lógica (`processarComando()`): Bluetooth
    (`ESP_BT`) e **Serial USB** (`Serial`, 115200), consumidas por
    `processarFonte(Stream&, origem)` no `loop()`. O boot avisa
    "Controle por USB (Serial) tambem ativo: A/F" e pede para fechar o Monitor Serial
    (a porta COM é exclusiva). Serve para testar sem emparelhar nada.
    Bytes fora de `'A'`/`'F'` (`\n`, `\r`, lixo) são ignorados e **não** renovam o
    failsafe, valendo para as duas origens. `BluetoothSerial` está depreciada no core
    3.3.11: o aviso é silenciado com `#pragma GCC diagnostic` (cosmético) só na linha da
    declaração.
  - `barco/README.md` — pinos, protocolo A/F, como rodar, firmware e avisos; traz a seção
    **"Teste sem Bluetooth (pelo USB)"** (gravar, fechar o Monitor Serial, achar a COM do
    CP210x/CH340 ou usar `--listar`, rodar com `--porta COMx`, o que deve acontecer) e a
    seção **"Se o BARCO não aparecer/conectar no Bluetooth"** (8 passos: gravar de verdade,
    Monitor Serial 115200, cabo com dados, Windows 11 24H2/25H2 com "Mostrar todos os
    dispositivos"/descoberta Avançado e remoção de pareamentos antigos em Configurações e
    em `control printers`, teste com fone Bluetooth para provar Classic no PC, brownout,
    chip sem BT Classic, plano B pelo USB). Traz também a subseção **"Aparece, mas fica
    'Não conectado'"**: em SPP o vínculo só nasce quando um programa abre a porta COM
    (conferir a COM em `control printers`/`Win32_SerialPort` e rodar
    `python leitura_mao_barco.py --porta COMx`); sem porta COM = pareamento pela metade
    (remover no Windows, reiniciar o BT, regravar e parear de novo); e a `BluetoothSerial`
    aceita **um cliente por vez** (celular/outro PC conectado bloqueia o seu).
- `requirements.txt` — dependências Python fixadas (`mediapipe>=0.10.30,<0.11`,
  `opencv-python>=4.9`, `pyserial>=3.5`); instalar com `pip install -r requirements.txt`
  (Python 3.10+, testado em 3.14.6).
- `.gitattributes` — normaliza fim de linha (`* text=auto eol=lf`) entre Windows/Linux/macOS.
- `LICENSE` — licença MIT (2026, Kaike, Maria e Marcos — Projeto Lito), referenciada no README.
- `modelo/drone.glb|.stl|.zip` — modelo 3D do drone.
- `README.md` — documentação completa em 11 seções: arquitetura (pipeline
  detecção → classificação → votação → envio), seção "A Homenagem" com fotos
  oficiais do Lito Sousa (avatar do canal no hero, foto Lito e Mila, retrato
  Voe Sem Medo e banner do canal — hotlinkadas do YouTube), gestos com as
  imagens de `leitura/direcoes/*.jpg`, contrato Bluetooth (T/F/E/D/C/B +
  `'1'`/`'0'`, COM4 9600), hardware corrigido e unificado no motor 8520 mini
  coreless (com capacitores, diodos 1N4148 e resistores 10 kΩ na lista),
  tabelas de pinos e rotação dos motores, fluxo de energia, modelo 3D
  (`modelo/drone.*`), guia de execução passo a passo, roadmap e créditos
  com os links oficiais do canal.

### Contrato de comandos Bluetooth

Enviados pelo `leitura_mao.py`: um byte por mudança de direção confirmada **e reenvio da
mesma letra a cada 0,5 s** enquanto o gesto se mantém (o sketch trata repetição como
comando idempotente — só renova o failsafe de 2 s):

| Letra | Direção  |
|:-----:|:---------|
| `T`   | TRÁS     |
| `F`   | FRENTE   |
| `E`   | ESQUERDA |
| `D`   | DIREITA  |
| `C`   | CIMA     |
| `B`   | BAIXO    |

Extras mantidos para o `testebluetooth.py`: `'1'` liga o LED (aceso em regime, sobrescrito
pelo próximo comando de direção), `'0'` desliga.
Porta no PC: **COM4** (`PORTA_BLUETOOTH`, ajustável no topo do script). Baudrate: **9600**.
Como descobrir a porta: Gerenciador de Dispositivos → Portas (COM e LPT) → "Standard Serial over Bluetooth link (COMx)".

### Gestos

- **tras**: as duas mãos abertas.
- **frente**: as duas mãos fechadas.
- **esquerda:** mão esquerda fechada e mão direita aberta.
- **direita**: mão direita fechada e mão esquerda aberta.
- **cima/baixo** (exato): nas DUAS mãos, polegar + indicador fechados E médio + anelar +
  mindinho esticados; pulso esquerdo mais alto na tela → `cima`, direito mais alto → `baixo`
  (no OpenCV o eixo Y cresce para baixo; pulso = landmark 0).

## Histórico

### 2026-11-18 — Barco: limpeza de pareamentos e troubleshooting de conexão

**Solicitação**: o "BARCO" passou a aparecer no PC do usuário, mas fica como "Não
conectado" no Bluetooth (pedido de resumo: "aparece, mas não conecta").

**O que foi feito**:
- [x] `barco/barco.ino`: nova constante `#define LIMPAR_PAREAMENTOS 1` no topo (comentada:
      1 apaga os bonds no boot, 0 mantém) e, logo após `ESP_BT.begin("BARCO")`,
      `if (LIMPAR_PAREAMENTOS) { ESP_BT.deleteAllBondedDevices(); Serial.println(...); }`.
      Fica depois do `begin()` de propósito (a API de bond só funciona com o Bluetooth já
      iniciado). API confirmada em `BluetoothSerial.h` do core 3.3.11. O cabeçalho documenta
      o porquê (pareamento "pela metade" deixa o aparelho listado como "Não conectado").
- [x] Resto do firmware **intacto**: Bluetooth continua mínimo (só `begin()` + esse bloco
      condicional), protocolo A/F, Serial USB, pino 25, blink não bloqueante e failsafe
      de 2 s sem mudanças.
- [x] `barco/README.md`: seção renomeada para "Se o BARCO não aparecer/conectar no
      Bluetooth", bloco de boot atualizado com a linha de "Pareamentos antigos apagados" e
      nova subseção **"Aparece, mas fica 'Não conectado'"** — (1) em SPP esse estado é
      normal, o vínculo só nasce quando um programa abre a porta COM (conferir a COM em
      `control printers` → COM ports, ou `Get-CimInstance Win32_SerialPort`, e rodar
      `python leitura_mao_barco.py --porta COMx`); (2) sem porta COM = pareamento pela
      metade (remover no Windows, reiniciar o BT, regravar, parear de novo); (3) a
      `BluetoothSerial` aceita um cliente por vez (celular/outro PC bloqueia).
- [x] Compilação: `arduino-cli compile --fqbn esp32:esp32:esp32 --warnings all barco` →
      0 erros, 0 avisos (1.063.536 B flash / 81%, 41.892 B RAM / 12%).

**Arquivos alterados**: `barco/barco.ino`, `barco/README.md`, `contexto.md`.

**Pendências**:
- [ ] Usuário confirmar o pareamento limpo e a porta COM do BARCO (e que a conexão ativa
      quando o programa abre a COM).
- [ ] Depois de funcionar, voltar `LIMPAR_PAREAMENTOS` para `0` (com `1`, o pareamento bom
      é apagado a cada boot).

### 2026-11-18 — Barco: Bluetooth simplificado e teste por USB

**Solicitação**: em outros PCs o "BARCO" aparece, mas no PC do usuário não; copiar a parte
de Bluetooth do `esp32/esp32.ino` (LITO), que funciona. Também foi pedido um modo de teste
pela serial USB.

**O que foi feito**:
- [x] `barco/barco.ino`: Bluetooth **idêntico ao `esp32/esp32.ino`** — só
      `ESP_BT.begin("BARCO")` no `setup()`. Removidos `esp_bt_gap_set_scan_mode()`,
      `getNumberOfBondedDevices()`, retry com `ESP_BT.end()` (`BT_RETRY_MS`/`btPronto`),
      `hasClient()` no loop, `esp_read_mac()`/MAC e o bloco de diagnóstico pesado;
      `imprimirDiagnostico()` ficou com 2 linhas de texto (core + modelo do chip).
      O `#pragma GCC diagnostic` do aviso de deprecação do `BluetoothSerial` foi mantido
      (cosmético, não toca no rádio).
- [x] `barco/barco.ino`: A/F aceitos também pelo **Serial USB**. Lógica centralizada em
      `processarComando(char, origem)` e `processarFonte(Stream&, origem)`, chamada para
      `ESP_BT` e para `Serial` no `loop()`; boot avisa que o USB está ativo e pede para
      fechar o Monitor Serial. Protocolo, `'A'`/`'F'` idempotentes/silenciosos, lixo sem
      renovar failsafe, pino 25 em LOW no topo do `setup()`, LED 2 não bloqueante,
      `FAILSAFE_MS = 2000` e `delay(20)` **mantidos**.
- [x] `barco/leitura_mao_barco.py`: `argparse` com `--porta COMx` (padrão
      `PORTA_BLUETOOTH` = COM4), `--baud N` e `--listar` (usa `serial.tools.list_ports` e
      sai sem abrir a câmera). Baud automático (9600 na porta padrão, 115200 nas demais);
      `conectar_esp32(porta, baud)` com mensagens claras; HUD mostra `PORT: COMx` ou
      "sem link"; falha ao abrir segue só com a câmera, sem crash. Detecção, votação 4/5,
      reenvio de 0,5 s, imagens baixo/esquerda e teclas s/q não mudaram.
- [x] `barco/README.md`: nova seção "Teste sem Bluetooth (pelo USB)"; "Se o BARCO não
      aparecer no Bluetooth" reescrita sem os diagnósticos removidos, com o passo a passo
      de Windows 11 (botão "Mostrar todos os dispositivos"/descoberta Avançado em
      24H2/25H2, remover pareamentos antigos em Configurações e em `control printers`,
      testar um fone Bluetooth e usar `--porta COMx` como plano B).
- [x] Validação: `py_compile` OK; 17 checagens com serial falsa OK (COM4/9600,
      `--porta COM5`/115200, `--baud`, porta com erro, reenvio de 0,5 s, `--listar`);
      `arduino-cli compile --fqbn esp32:esp32:esp32 --warnings all barco` OK
      (1.062.804 B flash / 81%, 41.892 B RAM / 12%), sem erros nem avisos.

**Arquivos alterados**: `barco/barco.ino`, `barco/leitura_mao_barco.py`, `barco/README.md`,
`contexto.md`.

**Pendências**:
- [ ] Testar no PC do usuário: gravar o sketch, conferir o "BARCO" em *Adicionar
      dispositivo* e, se preciso, validar o caminho USB com `--porta COMx`.
- [ ] Se ainda não aparecer, revisar a descoberta do Windows (24H2/25H2) e apagar
      pareamentos antigos (`BARCO` em Configurações e portas SPP em `control printers`).

### 2026-11-18 — Barco: diagnóstico de Bluetooth que não anuncia

**Solicitação**: "não está aparecendo para eu me conectar com barco no bluetooth" (placa
ESP32 DevKit clássica; no PC não aparecia nem "BARCO" nem "LITO").

**O que foi feito**:
- [x] `barco/barco.ino`: bloco `imprimirDiagnostico()` no boot com core Arduino-ESP32,
      ESP-IDF, modelo/revisão/núcleos do chip, MAC Bluetooth (`esp_read_mac(ESP_MAC_BT)`) e
      heap livre — separa "firmware errado/não gravado" de "problema de rádio".
- [x] `iniciarBluetooth()`: checa o retorno `bool` de `ESP_BT.begin("BARCO")`, imprime
      `FALHOU` e tenta de novo a cada 3 s (`BT_RETRY_MS`, com `ESP_BT.end()`) sem travar o
      loop; no sucesso reforça o modo descobrível com
      `esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE)` e imprime
      o `esp_err_t` (o core 3.3.11 não tem `setDeviceName()`/`setDiscoverable()`).
- [x] Imprime dispositivos pareados (`getNumberOfBondedDevices()`) e as transições de
      `hasClient()` uma vez por mudança (só observabilidade).
- [x] Bytes fora de `'A'`/`'F'` agora são ignorados e **não** renovam o failsafe (antes
      qualquer byte renovava); LED passou a usar a flag `ledPendente` em vez de `0` como
      sentinela. Pino 25, protocolo A/F e `FAILSAFE_MS = 2000` mantidos.
- [x] `#pragma GCC diagnostic ignored "-Wdeprecated-declarations"` apenas na declaração do
      `BluetoothSerial` (depreciado no core 3.3.11).
- [x] `barco/README.md`: seção "Se o BARCO não aparecer no Bluetooth" (7 passos) e a saída
      exata do Monitor Serial.
- [x] Compilação: `arduino-cli compile --fqbn esp32:esp32:esp32 --warnings all barco` →
      0 erros, 0 avisos (1.064.404 B flash / 81%, 41.908 B RAM / 12%).

**Arquivos alterados**: `barco/barco.ino`, `barco/README.md`, `contexto.md`.

**Pendências**:
- [ ] Teste em hardware: gravar o sketch, abrir o Monitor Serial em 115200 e reportar a
      saída do bloco de diagnóstico (principalmente o resultado de `begin()` e o MAC BT)
      para confirmar se o "BARCO" passa a aparecer no PC.
- [ ] Se continuar sem anunciar, verificar no Serial se a placa é ESP32 clássico (S2/S3/C3
      não têm Bluetooth Classic) e se há brownout/reset em loop.

### 2026-11-18 — Barco: imagens de estado na leitura

**Solicitação**: "adicione para a leitura mostrar a imagem baixo.jpg para quando mandar o
sinal e esquerda.jpg quando não enviar nada" (na pasta `barco/`).

**O que foi feito**:
- [x] `barco/leitura_mao_barco.py`: nova janela fixa **`estado`**, separada da janela
      `captura` e posicionada à direita do vídeo, mostrando a imagem do estado
      **confirmado** vindo de `../leitura/direcoes/`: `'A'` (duas mãos abertas, pino 25
      LIGADO) → `baixo.jpg`; `'F'` (pino 25 DESLIGADO) → `esquerda.jpg`; estado ainda não
      confirmado (`None`) também mostra `esquerda.jpg` (nada sendo enviado), sem enviar
      nenhuma letra.
- [x] Imagens carregadas no início (`carregar_imagens()`), com aviso claro e sem crash se
      faltarem; redimensionadas para altura máxima de 480 px mantendo a proporção;
      `imshow` só quando o conteúdo muda; fechamento no "X" tolerado (não reabre à força,
      não derruba); HUD mostra `img: baixo.jpg` / `img: esquerda.jpg`;
      `destroyAllWindows()` do `finally` cobre a nova janela.
- [x] Protocolo A/F, votação, reenvio de 0,5 s, failsafe e pinos **não mudaram**.
- [x] `barco/README.md`: nova seção curta "Imagem de referência" (janela `estado`,
      `baixo.jpg` com `'A'`, `esquerda.jpg` com `'F'`, imagem faltando e fechar no X).
- [x] Validação: `py_compile` OK; cenários com stubs OK (`'A'` → baixo, `'F'` → esquerda,
      `None` → esquerda no primeiro frame, sem `imshow` repetido, imagem inexistente sem
      crash, troca A→F na mesma janela, "X" não reabre).

**Arquivos alterados**: `barco/leitura_mao_barco.py`, `barco/README.md`, `contexto.md`.

**Pendências**:
- [ ] Nenhuma nova; seguem as pendências de hardware já registradas na entrada da pasta
      `barco/` (teste com câmera + ESP32 real, conferir pino 25/LED do pino 2, ajustar
      `PORTA_BLUETOOTH` e calibrar `MIN_DEDOS_ABERTOS`).

### 2026-11-18 — Pasta barco: teste das duas mãos abertas acionando o GPIO 25

**Solicitação**: "só para teste, crie uma pasta chamada barco e nessa crie um novo código de
leitura da mão como o da pasta leitura que leia se as duas mãos estão abertas ou não, se
estiverem mande energia para o pino 25".

**O que foi feito**:
- [x] Criada a pasta `barco/`, separada do drone (nada de `leitura/` ou `esp32/` foi alterado).
- [x] `barco/leitura_mao_barco.py`: detector standalone com o mesmo padrão de
      `leitura/leitura_mao.py` (MediaPipe HandLandmarker em modo VIDEO, 2 mãos, suavização
      de pontos, timestamp monotônico, votação e pyserial opcional), mas com regra simples:
      mão aberta = ≥4 dos 5 dedos esticados (polegar medido por distância ao pulso),
      confiança de lado ≥0,8; `'A'` só com **exatamente 2 mãos, ambas abertas**, qualquer
      outro caso `'F'`; votação 4 de 5 (`JANELA_VOTACAO=5`, `VOTOS_MINIMOS=4`); envio na
      mudança + reenvio a cada 0,5 s (`INTERVALO_REENVIO`) por causa do failsafe; falha de
      escrita derruba o link com aviso único; HUD com nº de mãos, estado de cada mão e
      "PIN 25: LIGADO/DESLIGADO"; teclas `s`/`q`; `PORTA_BLUETOOTH = "COM4"`, `BAUDRATE = 9600`.
- [x] `barco/barco.ino`: receptor Bluetooth Serial **"BARCO"** (não conflita com o "LITO"),
      `PINO_SAIDA = 25` em LOW no topo do `setup()`, `'A'` → HIGH, `'F'` → LOW, comando
      repetido idempotente/silencioso (`ultimoComando`), LED 2 não bloqueante,
      `FAILSAFE_MS = 2000` (zera `ultimoComando`), `while (ESP_BT.available())` + `delay(20)`.
      Sem PWM: apenas liga/desliga.
- [x] `barco/README.md` com pinos, protocolo A/F, como rodar, firmware e avisos.
- [x] `README.md`: `barco/` acrescentado à árvore "Estrutura do Repositório".
- [x] Validação: `py_compile` OK; 5 cenários com stubs OK (2 abertas → `'A'` após votação;
      1 aberta + 1 fechada → `'F'`; 1 mão → `'F'`; reenvio de 0,5 s; link caindo não crasha);
      `arduino-cli compile --fqbn esp32:esp32:esp32 barco` OK (1.061.868 B flash / 81%,
      41.892 B RAM / 12%). Nada testado em hardware.

**Arquivos alterados**: `barco/leitura_mao_barco.py` (novo), `barco/barco.ino` (novo),
`barco/README.md` (novo), `README.md`, `contexto.md`.

**Pendências**:
- [ ] Testar em hardware real (câmera + ESP32 emparelhado como "BARCO").
- [ ] Conferir o pino 25 na montagem e o LED do pino 2 (strapping pin: LED ao GND com resistor).
- [ ] Ajustar `PORTA_BLUETOOTH` (`COM4` é o padrão) se o COM do "BARCO" for outro.
- [ ] Calibrar `MIN_DEDOS_ABERTOS` se a detecção de mão aberta oscilar com as mãos reais.

### 2026-11-18 — Auditoria dos códigos e correções de robustez

**Solicitação**: "verifique caso haja algo para melhorar ou arrumar nos códigos" — e, após a
auditoria, corrigir TUDO (críticos, médios e baixos).

**O que foi feito**:
- [x] **Crítico C1/C2 (gesto parado desligava os motores):** `INTERVALO_REENVIO = 0.5` — a
      direção confirmada passa a ser **reenviada a cada 0,5 s** enquanto o gesto se mantém
      (o failsafe do ESP32 derruba os motores após 2 s sem bytes). `processar_envio()` só
      marca a "última enviada" quando `enviar_comando()` confirma o envio, então o throttle
      não engole mais o comando novo, e falha de escrita marca `esp32 = None` e avisa uma vez.
- [x] **Crítico C3 (script com acento no nome):** `leitura/leitura_mão.py` renomeado para
      `leitura/leitura_mao.py` (sem acento) e refatorado em `main()` +
      `if __name__ == "__main__"`, com `processar_frame`, `carregar_imagens`,
      `criar_detector`, `conectar_esp32`, `exibir_captura` e `processar_envio`.
- [x] **Médios:** `import serial` opcional (roda sem pyserial, só com a câmera); checagem da
      existência do `hand_landmarker.task` antes de criar o detector; timestamp monotônico
      (`time.perf_counter_ns()`) no modo VIDEO; janelas do OpenCV protegidas
      (`cv2.getWindowProperty` / `cv2.error`); câmera ausente → `sys.exit(1)`; `try/finally`
      liberando câmera, janelas e detector; Ctrl+C encerra limpo.
- [x] **Baixos:** comentário do `BAUDRATE` corrigido (SPP não usa baudrate); polegar
      classificado por **distância ao pulso** (funciona com a mão girada); suavização
      resetada após 2 frames sem a mão; desempate da votação pelo **voto mais recente**;
      stdout reconfigurado para UTF-8 tolerante; `testebluetooth.py` com `with serial.Serial`
      + `except (Exception, KeyboardInterrupt)` + `finally`.
- [x] **Sketch `esp32/esp32.ino`:** blink **não bloqueante** (`ledApagarEm` desligado no fim do
      `loop()`, sem `delay(60)`); `ultimoComando` torna o comando repetido **idempotente e
      silencioso** (só renova o failsafe); failsafe de 2 s **zera `ultimoComando`**; comentário
      do LED/GPIO2 (strapping pin, LED para GND com resistor); decisão de **não** usar
      `hasClient()` documentada em comentário no próprio sketch.
- [x] **Docs:** `README.md` corrigido no ponto **perigoso** de alimentação (3,3 V do regulador,
      LiPo na entrada, nunca no pino 3V3 — máx. ~3,6 V) + aviso em 7.8; removidas as afirmações
      de PWM como estado atual (hoje on/off; PWM e PID foram para o roadmap); "3 etapas" → 4;
      LED (GPIO2) na tabela de pinos; instalação via `requirements.txt`; contrato documentando o
      reenvio de 0,5 s e o failsafe de 2 s; árvore do repositório com `requirements.txt` e
      `LICENSE`; todas as referências ao script atualizadas. `esp32/README.md` idem.
- [x] **Novos arquivos:** `requirements.txt` (`mediapipe>=0.10.30,<0.11`,
      `opencv-python>=4.9`, `pyserial>=3.5`), `.gitattributes` (`* text=auto eol=lf`) e
      `LICENSE` (MIT, 2026). `.gitignore` ganhou `.venv/`, `venv/`, `Thumbs.db`, `.DS_Store`,
      `*.log` e `build/`.
- [x] **Validação:** `python -m py_compile` OK nos dois scripts; 3 cenários de teste da lógica
      de envio OK (gesto mantido 3 s → 7 envios de 0,5 em 0,5 s; troca de direção dentro da
      janela não se perde; falha de escrita não marca enviado e derruba o link); sketch
      compila com `arduino-cli` (81% flash, 12% RAM).

**Arquivos alterados**: `leitura/leitura_mão.py` → `leitura/leitura_mao.py` (renomeado e
refatorado), `leitura/testebluetooth.py`, `esp32/esp32.ino`, `esp32/README.md`, `README.md`,
`requirements.txt` (novo), `.gitattributes` (novo), `LICENSE` (novo), `.gitignore`, `contexto.md`.

**Pendências**:
- [ ] Testar em hardware real: câmera + Bluetooth em `COM4` (`PORTA_BLUETOOTH`).
- [ ] **TESTE SEM HÉLICES** antes de qualquer teste com os motores ligados.
- [ ] Carregar o sketch `esp32/esp32.ino` na placa (a compilação já está validada).
- [ ] Instalar as dependências com `pip install -r requirements.txt` (inclui o `pyserial`).
- [ ] Calibrar a leitura do polegar (distância ao pulso) se oscilar com as mãos reais.

### 2026-11-18 — Sketch do ESP32 movido para a pasta esp32/

**Solicitação**: "bote as coisas referentes ao esp32 em uma pasta".

**O que foi feito**:
- [x] `esp32` (arquivo solto na raiz) movido para `esp32/esp32.ino` — conteúdo idêntico
      (6979 bytes), preservado como rename pelo Git. A IDE Arduino exige que o sketch
      esteja numa pasta com o mesmo nome do arquivo `.ino`.
- [x] Criado `esp32/README.md` com pinos (FD=25, TD=26, TE=33, FE=32, LED=2), tabela de
      comandos (E/D/F/T/C/B e `1`/`0`), aviso "teste SEM hélices", failsafe de 2000 ms e
      instruções de compilação/carga.
- [x] `README.md` atualizado nos pontos que citavam o sketch na raiz: nota do modo de teste,
      nota do failsafe, passo "carregue o sketch" e a árvore "Estrutura do Repositório".
- [x] Corrigida a nota de Baudrate do Contrato Bluetooth: `9600` é o valor usado pelo Python
      na porta COM; o Bluetooth Serial (SPP) não usa baudrate (`ESP_BT.begin("LITO")`) e o
      `Serial.begin(115200)` é só do Monitor Serial USB.
- [x] Compilação validada com `arduino-cli` 1.5.1 / core `esp32:esp32 3.3.11` no novo
      caminho: sucesso (81% flash, 12% RAM).

**Arquivos alterados**: `esp32` → `esp32/esp32.ino` (rename), `esp32/README.md` (novo),
`README.md`, `contexto.md`.

**Pendências**:
- [ ] Carregar o sketch na placa via IDE Arduino.
- [ ] Testar com a eletrônica/motores reais, sempre **SEM hélices**.
- [ ] Migrar de on/off para PWM (controle de velocidade).
- [x] ~~Ajustar o comentário de `BAUDRATE = 9600`~~ — **resolvido em 2026-11-18**: o
      comentário agora explica que o Bluetooth Serial (SPP) não usa baudrate e que o valor
      só precisa ser aceito pelo driver da porta COM virtual.

### 2026-11-18 — Controle dos motores no sketch do ESP32 (modo teste)

**Solicitação**: fazer o sketch do ESP32 realmente acionar os motores em vez de apenas
imprimir a direção: esquerda liga só os motores da esquerda, direita só os da direita,
baixo nenhum, cima todos, e assim por diante.

**O que foi feito**:
- [x] `esp32` passa a acionar os 4 motores em modo de TESTE on/off (`HIGH` = ligado),
      cada GPIO no Gate de um MOSFET IRLB4132, conforme o mapeamento pedido:
      `E` → TE (33) + FE (32); `D` → FD (25) + TD (26); `F` → FD (25) + FE (32);
      `T` → TD (26) + TE (33); `C` → todos os 4; `B` → nenhum.
- [x] Funções novas `ligarMotores(fd, td, te, fe)` e `pararMotores()`, com constantes
      `MOTOR_FD=25`, `MOTOR_TD=26`, `MOTOR_TE=33`, `MOTOR_FE=32`; `pinMode(OUTPUT)` e
      motores em `LOW` logo no início do `setup()` (nunca inicia com motor ligado).
- [x] Serial passa a imprimir qual conjunto de motores ligou em cada comando.
- [x] Failsafe: `FAILSAFE_MS = 2000` com `millis()` (sem `delay` extra) — 2 s sem
      nenhum byte Bluetooth desligam todos os motores e avisam no Serial.
- [x] `'1'`/`'0'` continuam apenas o LED do pino 2, sem tocar nos motores.
- [x] Contrato Bluetooth mantido 100%: nome "LITO", mesmas letras,
      `while (ESP_BT.available())` e `delay(20)`.
- [x] Compilação validada com `arduino-cli` 1.5.1 / core `esp32:esp32 3.3.11`
      (FQBN `esp32:esp32:esp32`): sucesso, sem erros.
- [x] `README.md`: tabela do "Contrato Bluetooth" (seção 6) ganhou a coluna de efeito
      nos motores + nota sobre o modo de teste on/off (MOSFET IRLB4132, sem PWM) e o
      aviso de testar **sem hélices**.

**Arquivos alterados**: `esp32`, `README.md`, `contexto.md`.

**Pendências**:
- [ ] Testar com a eletrônica/motores reais, sempre **SEM hélices**.
- [ ] Depois migrar de on/off para PWM (controle de velocidade).
- [ ] Confirmar o mapeamento dos pinos na montagem física (FD=25, TD=26, TE=33, FE=32).

### 2026-10-24 — Envio único pós-votação, caminhos robustos e comandos no ESP32

**Solicitação**: fechar o ciclo de melhorias na leitura de mãos e no sketch do ESP32
(NameError sem Bluetooth, envio repetido de comandos, caminhos frágeis, gesto cima/baixo
promíscuo e atraso de 1 s por byte no ESP32); revisar, documentar em `contexto.md`,
commitar e enviar.

**O que foi feito**:
- [x] Corrigido `NameError` no `leitura/leitura_mao.py` quando o COM4 não conecta
      (`esp32 = None`; programa roda só com câmera).
- [x] Envio serial centralizado em `enviar_comando()`, único e só após a votação confirmar
      a direção; `direcao()` ficou pura (só retorna o nome); throttle de 0,5 s.
- [x] Caminhos das imagens e do modelo relativos ao script (pathlib, `PASTA_SCRIPT`),
      com avisos no boot.
- [x] Gesto cima/baixo agora exato: polegar+indicador fechados E médio+anelar+mindinho
      esticados nas duas mãos.
- [x] Constantes `PORTA_BLUETOOTH = "COM4"` e `BAUDRATE = 9600` no topo, com comentário
      sobre descobrir a porta.
- [x] Docstring de cabeçalho descrevendo a arquitetura (detecção → classificação →
      votação → envio na mudança).
- [x] `esp32`: loop esvazia todos os bytes com `while(ESP_BT.available())` e `delay(20)`
      (antes atrasava 1 s por char).
- [x] `esp32`: `switch` com T/F/E/D/C/B imprimindo o nome da direção e blink no LED pino 2;
      mantidos `'1'`/`'0'` do `testebluetooth.py`; byte desconhecido avisa.
- [x] Teste de lógica com stubs passou (fora do repositório, em pasta temporária).
- [x] `contexto.md` criado e `.gitignore` adicionado (`__pycache__`, `.opencode/`).

**Arquivos alterados**: `leitura/leitura_mao.py`, `esp32`, `contexto.md` (novo), `.gitignore` (novo).

**Pendências**:
- [ ] Confirmar se a porta do Bluetooth é COM4 (ajustar `PORTA_BLUETOOTH` no topo de
      `leitura/leitura_mao.py` se não for).
- [ ] Testar o gesto cima/baixo com as mãos reais (agora é mais rigoroso) e calibrar se precisar.
- [x] Compilar o sketch `esp32` — **validado** com `arduino-cli` (core `esp32:esp32 3.3.11`,
      FQBN `esp32:esp32:esp32`, sem erros; recompilado em 2026-11-18 após as correções de
      blink/failsafe: 81% flash, 12% RAM). A carga na placa segue na entrada de 2026-11-18.
- [ ] Futuro: comandos de rotação no próprio eixo (horário/anti-horário) citados no README.

### 2026-10-24 — Reescrita completa do README

**Solicitação**: melhorar o README; projeto é um drone controlado por reconhecimento
de mãos em homenagem ao Lito Sousa (canal Aviões e Músicas).

**O que foi feito**:
- [x] Day redesenhou o README por completo: hero centralizado com
      "Saudações Aeronáuticas!" — Lito Sousa e homenagem ao canal
      [Aviões e Músicas](https://www.youtube.com/@AvioesEMusicas); badges
      (Python, OpenCV, MediaPipe, ESP32, Arduino, Bluetooth); seções
      numeradas de 1 a 10 sem saltos (Sobre, Equipe, Como Funciona com
      diagrama ASCII do pipeline, Gestos, Contrato Bluetooth, Hardware,
      Modelo 3D, Como Executar, Estrutura do Repositório, Roadmap e Créditos).
- [x] Gestos documentados com as imagens de `leitura/direcoes/*.jpg`
      (verificadas: tras, frente, esquerda, direita, cima e baixo existem).
- [x] Contrato Bluetooth documentado (T/F/E/D/C/B + `'1'`/`'0'` de teste,
      COM4 9600, com dica para descobrir a porta).
- [x] Hardware corrigido: typo "quantidadde" corrigido; motor 8025 da seção
      antiga unificado para 8520 mini coreless conforme tabela de componentes;
      adicionados à lista capacitores 100/220 µF e 10/22 µF, diodos 1N4148 x4
      e resistores 10 kΩ (pull-down).
- [x] Tabelas de pinos e rotação dos motores, fluxo de energia e observações
      de segurança reorganizadas na seção de Hardware.
- [x] Seção Modelo 3D (`modelo/drone.glb|.stl|.zip`) e guia "Como Executar"
      (dependências pip, carregar sketch na IDE Arduino, emparelhar "LITO",
      porta COM4, rodar `leitura/leitura_mao.py`).
- [x] Roadmap atualizado (rotação no próprio eixo; vídeos pós-feira).

**Arquivos alterados**: `README.md`, `contexto.md`.

**Pendências**:
- [ ] Confirmar se a porta do Bluetooth é COM4 (ajustar `PORTA_BLUETOOTH` no topo de
      `leitura/leitura_mao.py` se não for).
- [ ] Testar o gesto cima/baixo com as mãos reais (agora é mais rigoroso) e calibrar se precisar.
- [ ] Compilar/carregar o sketch `esp32` na placa via IDE Arduino (nunca testado).
- [ ] Futuro: comandos de rotação no próprio eixo (horário/anti-horário) citados no README.
- [ ] Anexar vídeos de funcionamento após a feira de ciências.
- [ ] Confirmar o modelo real do motor (8520 vs 8025 apareciam inconsistentes no
      README antigo; hoje tudo unificado em 8520).

### 2026-10-24 — Fotos do Lito Sousa no README

**Solicitação**: adicionar fotos do Lito para não perder o foco da homenagem.

**O que foi feito**:
- [x] Monica pesquisou e testou URLs oficiais (avatar yt3, banner yt3,
      thumbnails ytimg dos vídeos 5EXbT-exVzE e 8AMu8XXIdfs — todas HTTP 200,
      sem token que expire).
- [x] Day criou a seção "2. ✈️ A Homenagem" com as fotos + avatar redondo no
      hero + links oficiais nos créditos; seções renumeradas de 1 a 11
      (com 7.1–7.8 e 9.1–9.4) e âncora do Contrato Bluetooth atualizada (## 6).
- [x] Bebell verificou: seções 1–11 contínuas e créditos com links oficiais
      confirmados no arquivo final.
- [x] Tom calibrado respeitando o momento atual do Lito (legado vivo pela
      família, sem menção à doença).

**Arquivos alterados**: `README.md`, `contexto.md`.

**Pendências**:
- [ ] Confirmar se a porta do Bluetooth é COM4 (ajustar `PORTA_BLUETOOTH` no topo de
      `leitura/leitura_mao.py` se não for).
- [ ] Testar o gesto cima/baixo com as mãos reais (agora é mais rigoroso) e calibrar se precisar.
- [ ] Compilar/carregar o sketch `esp32` na placa via IDE Arduino (nunca testado).
- [ ] Futuro: comandos de rotação no próprio eixo (horário/anti-horário) citados no README.
- [ ] Anexar vídeos de funcionamento após a feira de ciências.
- [ ] Confirmar o modelo real do motor (8520 vs 8025 apareciam inconsistentes no
      README antigo; hoje tudo unificado em 8520).
- [ ] Avatares/banners do YouTube podem mudar se o canal alterar imagem de
      perfil/capa — revisar visual do README na página do GitHub depois do
      push e trocar de URL se algo quebrar.

## Modelo para novas entradas

```
### AAAA-MM-DD — Título curto da tarefa

**Solicitação**: <pedido original, resumido>

**O que foi feito**:
- [x] <passo>
- [x] <passo>

**Arquivos alterados**: <lista>

**Pendências**:
- [ ] <o que fica para depois>
```
