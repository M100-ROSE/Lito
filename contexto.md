# Contexto do Projeto Lito

Drone controlado por gestos das mãos: Python/MediaPipe/OpenCV no PC lê as mãos pela
câmera e envia comandos via Bluetooth Serial para um ESP32 (sketch Arduino na raiz,
arquivo `esp32`).

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
- `esp32` — sketch Arduino (receptor Bluetooth Serial, nome do dispositivo "LITO"):
  loop rápido (`delay(20)`) que esvazia QUALQUER byte disponível com `while(ESP_BT.available())`,
  `switch` com letras de direção (imprime o nome + blink no LED do pino 2) e, para
  compatibilidade com `testebluetooth.py`, `'1'` acende e `'0'` apaga o LED;
  byte desconhecido apenas avisa.
- `modelo/drone.glb|.stl|.zip` — modelo 3D do drone.
- `README.md` — visão geral, componentes, alimentação, pinos e fluxo de energia.

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
- [ ] Futuro: comandos de rotação no próprio eixo (horário/anti-horário) citados no README.

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
