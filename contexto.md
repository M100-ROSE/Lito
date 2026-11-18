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
4. **Envio** — `enviar_comando()` envia UMA letra ao ESP32 somente quando a direção
   confirmada MUDA, com throttle de 0,5 s (`INTERVALO_MINIMO_ENVIO`).
   Sem Bluetooth conectado (`esp32 = None`), o programa roda só com a câmera e avisa no boot.

### Arquivos-chave

- `leitura/leitura_mão.py` — programa principal (câmera + gestos + envio serial).
  - Constantes no topo: `PORTA_BLUETOOTH = "COM4"`, `BAUDRATE = 9600`.
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
  faz blink no LED do pino 2. **Failsafe** de `FAILSAFE_MS = 2000` com `millis()`: sem
  nenhum byte Bluetooth por 2 s, desliga todos os motores. Para compatibilidade com
  `testebluetooth.py`, `'1'` acende e `'0'` apaga **apenas o LED** (não tocam nos motores);
  byte desconhecido apenas avisa.
- `esp32/README.md` — pinos, tabela de comandos, failsafe e como compilar/carregar o sketch.
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

Enviados pelo `leitura_mão.py`, um byte por mudança de direção confirmada:

| Letra | Direção  |
|:-----:|:---------|
| `T`   | TRÁS     |
| `F`   | FRENTE   |
| `E`   | ESQUERDA |
| `D`   | DIREITA  |
| `C`   | CIMA     |
| `B`   | BAIXO    |

Extras mantidos para o `testebluetooth.py`: `'1'` liga o LED, `'0'` desliga.
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
- [ ] Ajustar o comentário de `BAUDRATE = 9600` em `leitura/leitura_mão.py`, que ainda diz
      "mesmo valor configurado no ESP32".

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
- [x] Corrigido `NameError` no `leitura_mão.py` quando o COM4 não conecta
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

**Arquivos alterados**: `leitura/leitura_mão.py`, `esp32`, `contexto.md` (novo), `.gitignore` (novo).

**Pendências**:
- [ ] Confirmar se a porta do Bluetooth é COM4 (ajustar `PORTA_BLUETOOTH` no topo de
      `leitura/leitura_mão.py` se não for).
- [ ] Testar o gesto cima/baixo com as mãos reais (agora é mais rigoroso) e calibrar se precisar.
- [ ] Compilar/carregar o sketch `esp32` na placa via IDE Arduino (nunca testado).
      _Atualização 2026-11-18: a COMPILAÇÃO foi validada com `arduino-cli` (core
      `esp32:esp32 3.3.11`, FQBN `esp32:esp32:esp32`, sem erros); falta apenas carregar
      na placa._
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
      porta COM4, rodar `leitura/leitura_mão.py`).
- [x] Roadmap atualizado (rotação no próprio eixo; vídeos pós-feira).

**Arquivos alterados**: `README.md`, `contexto.md`.

**Pendências**:
- [ ] Confirmar se a porta do Bluetooth é COM4 (ajustar `PORTA_BLUETOOTH` no topo de
      `leitura/leitura_mão.py` se não for).
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
      `leitura/leitura_mão.py` se não for).
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
