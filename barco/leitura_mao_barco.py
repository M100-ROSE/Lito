"""Barco (teste isolado) - leitura de mãos: "as DUAS mãos estão abertas?"

Este arquivo é um TESTE SEPARADO do drone. Não faz parte do firmware do
Lito e não substitui `leitura/leitura_mao.py`. Ele reaproveita o mesmo
padrão já validado lá (MediaPipe HandLandmarker em modo VIDEO, suavização
de pontos, votação contra flicker, pyserial opcional e reenvio periódico),
mas com uma regra bem mais simples:

    - 'A' -> existem EXATAMENTE 2 mãos confiáveis e as DUAS estão abertas
             => o firmware liga o pino 25.
    - 'F' -> qualquer outro caso (0 mãos, 1 mão, ou alguma mão fechada)
             => o firmware desliga o pino 25.

Protocolo: UMA letra por mensagem. A mesma letra é REENVIADA a cada
INTERVALO_REENVIO enquanto o estado confirmado não muda, porque o firmware
tem failsafe: sem nenhum byte por 2 s ele desliga a saída sozinho.

Sem Bluetooth conectado o programa continua rodando com a câmera; apenas
não envia comandos (avisa uma vez, sem travar).

Além da janela do vídeo, uma janela separada ("estado") mostra a imagem de
referência do estado confirmado: `baixo.jpg` quando o estado é 'A'
(pino 25 ligado) e `esquerda.jpg` quando é 'F' (pino 25 desligado). Antes
da primeira confirmação da votação (estado None) já aparece `esquerda.jpg`,
porque nesse momento nada está sendo enviado. As imagens vêm de
`leitura/direcoes/` e são apenas ilustrativas.
"""

import collections
import pathlib
import sys
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Em consoles Windows legados os acentos podem estourar UnicodeEncodeError.
# Reconfigurar o stdout evita que o teste morra só por causa de um print.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------
# pyserial é opcional: sem ele o programa roda só com a câmera.
# ---------------------------------------------------------------------
try:
    import serial
except ImportError:  # pragma: no cover - depende do ambiente do usuário
    serial = None

# =====================================================================
# CONSTANTES DE AJUSTE (calibre aqui)
# =====================================================================

# --- conexão Bluetooth Serial -----------------------------------------
# Gerenciador de Dispositivos -> Portas (COM e LPT) ->
# "Standard Serial over Bluetooth link (COMx)". Troque "COM4" pelo COMx
# que aparecer no SEU PC (o do ESP32 emparelhado como "BARCO").
PORTA_BLUETOOTH = "COM4"

# O Bluetooth Serial (SPP) não usa baudrate de verdade; o valor só precisa
# ser aceito pelo driver da porta COM virtual. Mantido em 9600 como no
# restante do projeto.
BAUDRATE = 9600

# --- protocolo ---------------------------------------------------------
LETRA_ABERTAS = "A"    # duas mãos abertas  -> pino 25 LIGA
LETRA_FECHADAS = "F"   # qualquer outro caso -> pino 25 DESLIGA

# --- classificação das mãos -------------------------------------------
# Uma mão conta como "aberta" se tiver pelo menos esta quantidade de dedos
# esticados (de 5). 4 é tolerante: perdemos 1 dedo por ruído/ângulo e a
# mão ainda é considerada aberta.
MIN_DEDOS_ABERTOS = 4

# Confiança mínima do MediaPipe para aceitar o lado da mão (Left/Right).
# Mãos com score menor são ignoradas, para não contar "2 mãos" com uma
# detecção duvidosa.
CONFIANCA_MINIMA_LADO = 0.8

# --- anti-flicker (votação) -------------------------------------------
# Observa as últimas JANELA_VOTACAO leituras e só confirma um estado quando
# ele aparece em pelo menos VOTOS_MINIMOS delas.
JANELA_VOTACAO = 5
VOTOS_MINIMOS = 4

# --- envio serial ------------------------------------------------------
# Reenvio da mesma letra enquanto o estado confirmado continua igual.
# Precisa ser MENOR que o failsafe do firmware (FAILSAFE_MS = 2000 ms).
INTERVALO_REENVIO = 0.5

# --- suavização dos pontos (mesma ideia do leitura_mao.py) ------------
ALPHA_SUAVIZACAO = 0.2  # peso do frame atual (1 = sem suavização)
FRAMES_ATE_RESET = 2    # frames sem a mão até descartar a suavização

# =====================================================================
# CAMINHOS
# =====================================================================
# Pasta deste script: funciona mesmo executando de outro diretório.
PASTA_SCRIPT = pathlib.Path(__file__).resolve().parent

# Modelo reaproveitado da pasta `leitura/` (não duplicamos o arquivo).
CAMINHO_MODELO = PASTA_SCRIPT.parent / "leitura" / "hand_landmarker.task"

# Imagens de referência reaproveitadas da pasta `leitura/direcoes/`
# (mesmos arquivos usados pelo teste do drone).
PASTA_IMAGENS = PASTA_SCRIPT.parent / "leitura" / "direcoes"

# Estado confirmado -> arquivo de imagem exibido na janela "estado".
# 'A' (pino 25 LIGADO) mostra como fazer o gesto; 'F' (DESLIGADO) mostra
# a alternativa. Fotos originais são grandes: reduzimos ao carregar.
IMAGEM_POR_ESTADO = {
    LETRA_ABERTAS: "baixo.jpg",
    LETRA_FECHADAS: "esquerda.jpg",
}

# Altura máxima da imagem na tela (mantendo a proporção).
ALTURA_MAXIMA_IMAGEM = 480

# Nome FIXO da janela da imagem: trocamos o conteúdo, nunca criamos uma
# janela nova por letra.
NOME_JANELA_ESTADO = "estado"

# Imagens carregadas: {nome_do_arquivo: ndarray já redimensionado}
IMAGENS_ESTADO = {}

# Qual arquivo está sendo exibido agora (None = nenhum) e se a janela foi
# fechada pelo usuário no X (nesse caso não reabrimos à força).
imagem_exibida = None
janela_estado_descartada = False

# Largura do frame atual da câmera, usada para posicionar a janela da
# imagem logo à direita da janela do vídeo.
largura_atual = 0

# =====================================================================
# ESTADO GLOBAL
# =====================================================================

# Conexão serial (None = sem Bluetooth, modo somente câmera).
esp32 = None

# Evita repetir a mensagem de link morto a cada frame.
aviso_link_morto = False

# Última letra EFETIVAMENTE enviada com sucesso (None = nenhuma ainda).
ultima_enviada = None

# Instante (time.monotonic) do último envio bem-sucedido.
ultimo_envio = float("-inf")

# --- landmarks ---------------------------------------------------------
# ordem: polegar, indicador, médio, anelar, mindinho
DEDOS = [
    {"nome": "polegar", "ponta": 4, "articulacao": 3},
    {"nome": "indicador", "ponta": 8, "articulacao": 7},
    {"nome": "medio", "ponta": 12, "articulacao": 11},
    {"nome": "anelar", "ponta": 16, "articulacao": 15},
    {"nome": "mindinho", "ponta": 20, "articulacao": 19},
]

# Suavização por lado ("Right"/"Left") e contador de ausências.
pontos_suavizados = {"Right": None, "Left": None}
ausencias = {"Right": 0, "Left": 0}

# Cores BGR: mão direita roxa, esquerda vermelha (igual ao projeto).
COR_ROXA = (128, 0, 128)
COR_VERMELHA = (0, 0, 255)
COR_VERDE = (0, 200, 0)
COR_CINZA = (180, 180, 180)


# =====================================================================
# COMUNICAÇÃO SERIAL
# =====================================================================
def conectar_esp32():
    """Abre a porta serial do Bluetooth, se possível.

    Falha de conexão (ou pyserial ausente) NÃO é fatal: o teste segue em
    modo somente câmera. Avisa uma única vez.
    """
    global esp32, aviso_link_morto

    if serial is None:
        esp32 = None
        aviso_link_morto = True
        print("AVISO: pyserial não instalado (pip install pyserial). "
              "Rodando só com a câmera: nenhuma letra será enviada.")
        return

    try:
        esp32 = serial.Serial(PORTA_BLUETOOTH, BAUDRATE, timeout=1)
        print(f"Conectado ao barco na porta {PORTA_BLUETOOTH}.")
        time.sleep(2)
    except Exception as e:
        esp32 = None
        aviso_link_morto = True
        print(f"Sem conexão Bluetooth ({e}). Rodando SOMENTE CÂMERA "
              f"(ajuste PORTA_BLUETOOTH se o COM mudou).")


def enviar_comando(letra):
    """Envia uma única letra. True se o envio deu certo.

    Nunca lança exceção: em caso de falha avisa UMA vez, marca o link como
    morto (esp32 = None) e devolve False.
    """
    global esp32, aviso_link_morto

    if esp32 is None:
        if not aviso_link_morto:
            print(f"Sem conexão Bluetooth - letra '{letra}' não enviada.")
            aviso_link_morto = True
        return False

    try:
        esp32.write(letra.encode())
        return True
    except Exception as e:
        esp32 = None
        aviso_link_morto = True
        print(f"Conexão Bluetooth perdida ao enviar '{letra}': {e}. "
              "Seguindo só com a câmera.")
        return False


def processar_envio(estado_confirmado, agora):
    """Decide e executa no máximo UM envio por frame.

    - estado confirmado diferente da última letra enviada -> envia na hora
      (não existe throttle de troca: 'A' <-> 'F' deve ser imediato);
    - mesmo estado -> reenvia a letra a cada INTERVALO_REENVIO, para o
      failsafe do firmware não desligar o pino 25 sozinho;
    - estado None (votação ainda não confirmou nada) -> não envia.

    Só atualiza o estado interno se o envio realmente deu certo; se o link
    cair, a letra pendente é tentada de novo quando houver link.
    """
    global ultima_enviada, ultimo_envio

    if estado_confirmado is None:
        return

    if estado_confirmado == ultima_enviada:
        if agora - ultimo_envio < INTERVALO_REENVIO:
            return
    # estado diferente: envia imediatamente (primeira vez inclusive)

    if enviar_comando(estado_confirmado):
        ultima_enviada = estado_confirmado
        ultimo_envio = agora


# =====================================================================
# DETECTOR
# =====================================================================
def criar_detector():
    """Cria o HandLandmarker (modo VIDEO) ou encerra com mensagem clara."""
    if not CAMINHO_MODELO.is_file():
        print("ERRO: modelo do MediaPipe não encontrado.")
        print(f"Esperado em: {CAMINHO_MODELO}")
        print("O arquivo hand_landmarker.task deve ficar na pasta "
              "'leitura' do projeto.")
        sys.exit(1)

    base_options = python.BaseOptions(model_asset_path=str(CAMINHO_MODELO))
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=2,
        # modo VIDEO: usa o frame anterior como contexto (tracking), o que
        # é bem mais estável que detectar do zero a cada frame
        running_mode=vision.RunningMode.VIDEO,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.7,
        min_tracking_confidence=0.7,
    )
    return vision.HandLandmarker.create_from_options(options)


# =====================================================================
# CLASSIFICAÇÃO: dedos, mão aberta e estado do teste
# =====================================================================
def distancia(ponto_a, ponto_b):
    """Distância euclidiana entre dois landmarks normalizados."""
    return ((ponto_a.x - ponto_b.x) ** 2
            + (ponto_a.y - ponto_b.y) ** 2) ** 0.5


def dedo_esticado(mao, dedo, lado=None):
    """True se o dedo está esticado.

    Mesma lógica do leitura_mao.py: 4 dedos são comparados pelo eixo y
    (ponta acima da articulação); o polegar é comparado por DISTÂNCIA AO
    PULSO, para continuar correto com a mão girada.

    `lado` não é usado; existe só para manter a mesma assinatura.
    """
    ponta = mao[dedo["ponta"]]
    articulacao = mao[dedo["articulacao"]]

    if dedo["nome"] == "polegar":
        pulso = mao[0]
        return distancia(ponta, pulso) > distancia(articulacao, pulso)
    return ponta.y < articulacao.y


def contar_dedos_abertos(dedos):
    """Quantidade de dedos esticados (0 a 5) a partir dos 5 booleanos."""
    return sum(1 for esticado in dedos if esticado)


def mao_aberta(dedos):
    """True se a mão tem pelo menos MIN_DEDOS_ABERTOS dedos esticados."""
    return contar_dedos_abertos(dedos) >= MIN_DEDOS_ABERTOS


def estado_bruto(maos):
    """Classifica o frame em LETRA_ABERTAS ou LETRA_FECHADAS.

    `maos` é uma lista com uma entrada por mão CONFIÁVEL detectada, no
    formato {"score": float, "dedos": [bool x5]}. Entradas com score
    abaixo de CONFIANCA_MINIMA_LADO são descartadas aqui também (defesa
    dupla: quem monta a lista já filtra).

    Regra do teste: exatamente 2 mãos confiáveis E as duas abertas.
    Qualquer outro caso (0 mãos, 1 mão, 3+ improvável, alguma fechada)
    é LETRA_FECHADAS.
    """
    confiaveis = [m for m in maos if m["score"] >= CONFIANCA_MINIMA_LADO]

    if len(confiaveis) != 2:
        return LETRA_FECHADAS

    if all(mao_aberta(m["dedos"]) for m in confiaveis):
        return LETRA_ABERTAS

    return LETRA_FECHADAS


class VotacaoEstado:
    """Filtro anti-flicker: confirma um estado só com votos suficientes.

    Guarda as últimas JANELA_VOTACAO leituras e devolve o estado que
    aparece pelo menos VOTOS_MINIMOS vezes. Enquanto não houver essa
    maioria, devolve None (nada é enviado). Em empate, prefere o voto
    mais recente — responde melhor a mudanças reais.
    """

    def __init__(self, janela=JANELA_VOTACAO, minimo=VOTOS_MINIMOS):
        self.janela = janela
        self.minimo = minimo
        self.historico = collections.deque(maxlen=janela)

    def atualizar(self, estado):
        """Registra uma leitura e devolve o estado confirmado (ou None)."""
        self.historico.append(estado)

        contagem = collections.Counter(self.historico)
        max_votos = max(contagem.values())
        candidatos = [e for e, v in contagem.items() if v == max_votos]

        if len(candidatos) == 1:
            escolhido = candidatos[0]
        else:
            escolhido = None
            for voto in reversed(self.historico):
                if voto in candidatos:
                    escolhido = voto
                    break

        if escolhido is not None and max_votos >= self.minimo:
            return escolhido
        return None


def suavizar_pontos(lado, pontos_novos):
    """Média ponderada com os pontos do frame anterior (reduz tremedeira)."""
    anteriores = pontos_suavizados[lado]

    if anteriores is None or len(anteriores) != len(pontos_novos):
        pontos_suavizados[lado] = pontos_novos
        return pontos_novos

    resultado = []
    for (x_novo, y_novo), (x_antigo, y_antigo) in zip(pontos_novos, anteriores):
        x_suave = int(ALPHA_SUAVIZACAO * x_novo + (1 - ALPHA_SUAVIZACAO) * x_antigo)
        y_suave = int(ALPHA_SUAVIZACAO * y_novo + (1 - ALPHA_SUAVIZACAO) * y_antigo)
        resultado.append((x_suave, y_suave))

    pontos_suavizados[lado] = resultado
    return resultado


# =====================================================================
# PROCESSAMENTO DE UM FRAME
# =====================================================================
def processar_frame(captura, detector):
    """Detecta as mãos, desenha os pontos e devolve a leitura do frame.

    Retorna (captura, maos), onde `maos` é a lista descrita em
    estado_bruto() — já filtrada por CONFIANCA_MINIMA_LADO.
    """
    global largura_atual
    # espelha como um espelho/câmera selfie: o MediaPipe espera isso para
    # classificar Left/Right corretamente
    captura = cv2.flip(captura, 1)
    mp_captura = cv2.cvtColor(captura, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=mp_captura)

    # timestamp monotônico em ms (modo VIDEO exige sempre crescente)
    timestamp_ms = time.perf_counter_ns() // 1_000_000
    resultado = detector.detect_for_video(mp_image, timestamp_ms)

    altura, largura, _ = captura.shape
    largura_atual = largura

    maos = []
    vistas = {"Right": False, "Left": False}

    for indice_mao, mao in enumerate(resultado.hand_landmarks):
        categoria = resultado.handedness[indice_mao][0]
        lado = categoria.category_name  # "Left" ou "Right"
        score = categoria.score

        if score < CONFIANCA_MINIMA_LADO:
            continue  # detecção duvidosa: não conta como mão

        vistas[lado] = True
        cor = COR_ROXA if lado == "Right" else COR_VERMELHA

        pontos_brutos = []
        for ponto in mao:
            pontos_brutos.append((int(ponto.x * largura),
                                  int(ponto.y * altura)))

        pontos_da_mao = suavizar_pontos(lado, pontos_brutos)
        for (x, y) in pontos_da_mao:
            cv2.circle(captura, (x, y), 5, cor, -1)

        dedos = [dedo_esticado(mao, dedo, lado) for dedo in DEDOS]
        maos.append({"lado": lado, "score": score, "dedos": dedos})

    # mão ausente por alguns frames: descarta a suavização antiga
    for lado, vista in vistas.items():
        if vista:
            ausencias[lado] = 0
        else:
            ausencias[lado] += 1
            if ausencias[lado] >= FRAMES_ATE_RESET:
                pontos_suavizados[lado] = None

    return captura, maos


# =====================================================================
# HUD
# =====================================================================
def desenhar_hud(captura, maos, estado_confirmado, nome_imagem=None):
    """Escreve no frame: nº de mãos, estado de cada mão, o pino 25 e a
    imagem de referência exibida na janela "estado"."""
    y = 30
    cv2.putText(captura, f"Maos detectadas: {len(maos)}", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, COR_CINZA, 2)

    for mao in maos:
        y += 30
        nome = "Direita" if mao["lado"] == "Right" else "Esquerda"
        aberta = mao_aberta(mao["dedos"])
        texto = f"{nome}: {'ABERTA' if aberta else 'fechada'} " \
                f"({contar_dedos_abertos(mao['dedos'])} dedos)"
        cor = COR_VERDE if aberta else COR_CINZA
        cv2.putText(captura, texto, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 2)

    y += 40
    ligado = (estado_confirmado == LETRA_ABERTAS)
    texto_pino = "PIN 25: LIGADO" if ligado else "PIN 25: DESLIGADO"
    cv2.putText(captura, texto_pino, (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                COR_VERDE if ligado else COR_VERMELHA, 2)

    if nome_imagem:
        y += 28
        cv2.putText(captura, f"img: {nome_imagem}", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, COR_CINZA, 1)

    y += 30
    cv2.putText(captura, "'s' ou 'q' para sair", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COR_CINZA, 1)

    return captura


def janela_existe(nome):
    """True se a janela existe e está visível (protegido contra cv2.error)."""
    try:
        return cv2.getWindowProperty(nome, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


# =====================================================================
# IMAGENS DE REFERÊNCIA (janela "estado")
# =====================================================================
def redimensionar_para_tela(imagem):
    """Reduz a imagem para ALTURA_MAXIMA_IMAGEM, mantendo a proporção.

    As fotos originais têm alguns milhares de pixels de altura e abririam
    gigantes na tela. Imagens já menores que o limite ficam intactas.
    """
    altura, largura = imagem.shape[:2]
    if altura <= ALTURA_MAXIMA_IMAGEM:
        return imagem

    escala = ALTURA_MAXIMA_IMAGEM / float(altura)
    nova_largura = max(1, int(round(largura * escala)))
    return cv2.resize(imagem, (nova_largura, ALTURA_MAXIMA_IMAGEM),
                      interpolation=cv2.INTER_AREA)


def carregar_imagens():
    """Carrega baixo.jpg e esquerda.jpg em IMAGENS_ESTADO.

    Imagem faltando NÃO é fatal: avisa com o caminho procurado e o teste
    segue normalmente, apenas sem exibir a imagem daquele estado.
    """
    faltando = []
    for nome in sorted(set(IMAGEM_POR_ESTADO.values())):  # baixo, esquerda
        caminho = PASTA_IMAGENS / nome
        # cv2.imread devolve None em silêncio quando o arquivo não existe
        imagem = cv2.imread(str(caminho))
        if imagem is None:
            faltando.append(nome)
        else:
            IMAGENS_ESTADO[nome] = redimensionar_para_tela(imagem)

    if faltando:
        print("AVISO: não foi possível carregar a(s) imagem(ns) de referência:")
        for nome in faltando:
            print(f"  - {nome} (procurado em {PASTA_IMAGENS})")
        print("O teste continua, apenas sem exibir essa imagem.")


def mostrar_estado(estado_confirmado):
    """Reflete o estado CONFIRMADO na janela "estado" (nome fixo).

    Para efeito de EXIBIÇÃO, estado None (votação ainda não confirmou nada,
    ou seja, nada sendo enviado) é tratado como 'F': assim esquerda.jpg
    aparece desde o primeiro frame. O protocolo não muda — nada é enviado
    sem confirmação da votação.

    - estado sem imagem carregada -> não mexe na janela;
    - mesmo estado já exibido -> não reenvia imshow a cada frame;
    - estado diferente -> troca o conteúdo da MESMA janela;
    - usuário fechou no X -> esquecemos a janela e não reabrimos à força.
    """
    global imagem_exibida, janela_estado_descartada

    estado_exibicao = LETRA_FECHADAS if estado_confirmado is None else estado_confirmado
    nome_imagem = IMAGEM_POR_ESTADO.get(estado_exibicao)
    if nome_imagem is None or nome_imagem not in IMAGENS_ESTADO:
        return

    if janela_estado_descartada:
        return  # usuário fechou no X: não reabre à força

    if imagem_exibida is not None:
        if not janela_existe(NOME_JANELA_ESTADO):
            # fechada no X: não insiste, só esquece o que estava na tela
            janela_estado_descartada = True
            imagem_exibida = None
            return
        if imagem_exibida == nome_imagem:
            return  # conteúdo já correto: nada a fazer neste frame

    try:
        cv2.imshow(NOME_JANELA_ESTADO, IMAGENS_ESTADO[nome_imagem])
        # primeira exibição: posiciona à direita da janela do vídeo.
        # Nas trocas de estado a janela fica onde o usuário deixou.
        if imagem_exibida is None:
            cv2.moveWindow(NOME_JANELA_ESTADO, largura_atual + 50, 30)
        imagem_exibida = nome_imagem
    except cv2.error:
        # janela inválida/fechada no X: apenas para de tentar
        janela_estado_descartada = True
        imagem_exibida = None


# =====================================================================
# PROGRAMA PRINCIPAL
# =====================================================================
def main():
    carregar_imagens()
    conectar_esp32()
    detector = criar_detector()

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("ERRO: não foi possível abrir a câmera (índice 0).")
        print("Verifique se outra aplicação está usando a webcam ou se ela "
              "está conectada.")
        try:
            detector.close()
        except Exception:
            pass
        sys.exit(1)

    votacao = VotacaoEstado()
    posicionada = False

    try:
        while True:
            sucesso, captura = camera.read()
            if not sucesso:
                print("Não foi possível capturar a imagem da câmera.")
                break

            captura, maos = processar_frame(captura, detector)

            estado = votacao.atualizar(estado_bruto(maos))

            # janela separada com a imagem do estado CONFIRMADO (A/F)
            mostrar_estado(estado)

            captura = desenhar_hud(captura, maos, estado,
                                   imagem_exibida)

            try:
                cv2.imshow("barco - duas maos abertas", captura)
                if not posicionada:
                    cv2.moveWindow("barco - duas maos abertas", 0, 30)
                    posicionada = True
            except cv2.error:
                break

            if not janela_existe("barco - duas maos abertas"):
                break  # usuário fechou no X

            # único ponto que conversa com o firmware
            processar_envio(estado, time.monotonic())

            tecla = cv2.waitKey(25) & 0xFF
            if tecla in (ord("s"), ord("q")):
                break

    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário (Ctrl+C).")
    finally:
        camera.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        try:
            detector.close()
        except Exception:
            pass
        print("Câmera liberada. Teste encerrado.")


if __name__ == "__main__":
    main()
