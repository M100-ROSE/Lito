"""
Lito - leitura de mãos e controle do drone por gestos.

Arquitetura do programa (em 4 etapas):

    1. DETECÇÃO   -> MediaPipe HandLandmarker (modo VIDEO) encontra 2 mãos
                     por frame e devolve 21 landmarks de cada uma.
    2. CLASSIFICAÇÃO -> cada mão gera um vetor de 5 booleanos (dedos
                     esticados ou não) e a função direcao() decide qual
                     gesto está sendo feito. Essa função é PURA: só
                     devolve um nome ("tras", "frente", ...) ou None.
                     Ela NÃO conversa com o ESP32.
    3. VOTAÇÃO    -> direcao_estavel() mantém um histórico das últimas
                     leituras e só confirma uma direção quando ela vence
                     por voto majoritário. Isso elimina o flicker de
                     frames mal classificados.
    4. ENVIO      -> o comando Bluetooth é enviado quando a direção
                     CONFIRMADA muda (ex.: "tras" -> "esquerda") e também
                     REENVIADO a cada INTERVALO_REENVIO (0,5 s) enquanto a
                     mesma direção continuar confirmada. O reenvio é
                     necessário porque o ESP32 tem failsafe: sem nenhum
                     byte por 2 s ele desliga os motores. O contrato com o
                     firmware continua o mesmo: UMA letra por mensagem.
                     Quando nenhuma direção está confirmada (mãos fora de
                     cena), só atualizamos o estado interno.

Sem Bluetooth conectado o programa continua funcionando normalmente
(câmera + janelas + votação); apenas não envia comandos.
"""

import collections
import pathlib
import sys
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Em consoles Windows legados (cp850/cp1252) os acentos dos textos abaixo
# podem estourar UnicodeEncodeError. Reconfigurar o stdout para UTF-8 com
# "replace" evita que o programa morra só por causa de um print.
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

# --- conexão com o ESP32 via Bluetooth Serial -------------------------
# Como descobrir a porta: Gerenciador de Dispositivos -> Portas (COM e LPT)
# -> "Standard Serial over Bluetooth link (COMx)" -> anote o COMx.
PORTA_BLUETOOTH = "COM4"

# O Bluetooth Serial (SPP) NÃO usa baudrate: os bytes trafegam no ritmo do
# próprio protocolo. Esse valor só precisa ser aceito pelo driver da porta
# COM virtual do Windows; na prática qualquer valor comum (9600, 115200)
# funciona. Mantido em 9600 para casar com o que já era usado no projeto.
BAUDRATE = 9600

# guarda a conexão serial (None significa "sem Bluetooth, modo somente leitura")
esp32 = None

# evita repetir a mensagem de link morto a cada tentativa de envio
aviso_link_morto = False

# intervalo mínimo entre dois envios de comandos DIFERENTES (segundos)
INTERVALO_MINIMO_ENVIO = 0.5

# intervalo entre REENVIOS da mesma direção confirmada (segundos).
# Precisa ser menor que o failsafe do firmware (FAILSAFE_MS = 2000 ms),
# senão o ESP32 desliga os motores no meio de um gesto parado.
INTERVALO_REENVIO = 0.5

# --- caminhos (relativos à pasta do PRÓPRIO script) -------------------
# Usar a pasta do script (e não o diretório atual) faz o programa
# funcionar mesmo se for executado de outra pasta (ex.: raiz do projeto).
PASTA_SCRIPT = pathlib.Path(__file__).resolve().parent

PASTA_IMAGENS = PASTA_SCRIPT / "direcoes"
NOMES_IMAGENS = ["tras", "frente", "esquerda", "direita", "cima", "baixo"]
IMAGENS = {}

CAMINHO_MODELO = PASTA_SCRIPT / "hand_landmarker.task"

# --- estado da interface ----------------------------------------------
# guarda o nome da janela de direção que está aberta no momento (ou None)
janela_aberta = None

# largura do frame atual da câmera, usada para posicionar a janela de
# imagem à direita da janela de vídeo
largura_atual = 0

# controla se a janela "captura" já foi posicionada na tela
janela_captura_posicionada = False

# última direção EFETIVAMENTE ENVIADA com sucesso (ou None). Só é
# atualizada depois de enviar_comando() confirmar o envio.
ultima_enviada = None

# instante (time.monotonic) do último envio BEM-SUCEDIDO
ultimo_envio = float("-inf")

# confiança mínima para aceitar a classificação de qual mão é qual
CONFIANCA_MINIMA_LADO = 0.8

# cores em BGR (padrão do OpenCV)
COR_ROXA = (128, 0, 128)     # mão direita
COR_VERMELHA = (0, 0, 255)   # mão esquerda

# índices dos landmarks de cada dedo (ponta e articulação de referência)
# ordem: polegar, indicador, médio, anelar, mindinho
DEDOS = [
    {"nome": "polegar", "ponta": 4, "articulacao": 3},
    {"nome": "indicador", "ponta": 8, "articulacao": 7},
    {"nome": "medio", "ponta": 12, "articulacao": 11},
    {"nome": "anelar", "ponta": 16, "articulacao": 15},
    {"nome": "mindinho", "ponta": 20, "articulacao": 19},
]

# --- suavização dos pontos (reduz tremedeira visual e de posição) ---
ALPHA_SUAVIZACAO = 0.2  # peso do frame atual (0 = ignora o novo, 1 = sem suavização)
pontos_suavizados = {"Right": None, "Left": None}

# quantos frames consecutivos sem a mão até descartar a suavização antiga
# (evita "pontos voando" na tela quando a mão reaparece em outro lugar)
FRAMES_ATE_RESET = 2
ausencias = {"Right": 0, "Left": 0}

# --- estabilização da direção exibida (filtro de voto majoritário) ---
HISTORICO_TAMANHO = 7
VOTOS_MINIMOS = 4  # precisa aparecer pelo menos essa quantidade de vezes no histórico
historico_direcoes = collections.deque(maxlen=HISTORICO_TAMANHO)

# letra enviada ao ESP32 para cada direção confirmada
LETRAS_COMANDO = {
    "tras": "T",
    "frente": "F",
    "esquerda": "E",
    "direita": "D",
    "cima": "C",
    "baixo": "B",
}


# ---------------------------------------------------------------------
# Comunicação com o ESP32
# ---------------------------------------------------------------------
def conectar_esp32():
    """Abre a porta serial do Bluetooth, se possível.

    Falha de conexão (ou pyserial ausente) NÃO é fatal: o programa segue
    em modo somente leitura (câmera + janelas + votação).
    """
    global esp32, aviso_link_morto

    if serial is None:
        esp32 = None
        aviso_link_morto = True
        print("AVISO: pyserial não instalado (pip install pyserial). "
              "Rodando só com a câmera: nenhum comando será enviado.")
        return

    try:
        esp32 = serial.Serial(PORTA_BLUETOOTH, BAUDRATE, timeout=1)
        print(f"Conectado com sucesso ao ESP32 na porta {PORTA_BLUETOOTH}!")
        time.sleep(2)
    except Exception as e:
        esp32 = None
        aviso_link_morto = True
        print(f"Sem conexão com o ESP32 ({e}). Rodando SOMENTE LEITURA "
              f"(câmera e janelas funcionam, nenhum comando é enviado).")


def enviar_comando(letra):
    """Envia uma única letra ao ESP32. Devolve True se o envio deu certo.

    Não lança exceção: em caso de falha avisa UMA vez, marca o link como
    morto (esp32 = None) e devolve False, para que o chamador não
    considere o comando como enviado.
    """
    global esp32, aviso_link_morto

    if esp32 is None:
        if not aviso_link_morto:
            print("Sem conexão Bluetooth - comando não enviado:", letra)
            aviso_link_morto = True
        return False

    try:
        esp32.write(letra.encode())
        return True
    except Exception as e:
        esp32 = None
        aviso_link_morto = True
        print(f"Conexão Bluetooth perdida ao enviar '{letra}': {e}. "
              "Seguindo só com a câmera (nenhum comando novo será enviado).")
        return False


def processar_envio(direcao_confirmada, agora):
    """Decide e executa no máximo UM envio por frame.

    Regras (contrato de 1 letra por mensagem):
      - direção diferente da última ENVIADA -> espera INTERVALO_MINIMO_ENVIO
        desde o último envio e então manda a letra nova;
      - mesma direção ENVIADA (gesto mantido) -> reenvia a mesma letra a
        cada INTERVALO_REENVIO, para o failsafe do ESP32 não derrubar os
        motores;
      - direção None (mãos fora de cena) -> não envia nada e esquece a
        última enviada, para o próximo gesto ser enviado sem esperar.

    O estado só é atualizado quando enviar_comando() devolve True: se o
    Bluetooth cair, o comando pendente é tentado de novo assim que houver
    link (ou o link já está marcado como morto e nada mais é enviado).
    """
    global ultima_enviada, ultimo_envio

    letra = LETRAS_COMANDO.get(direcao_confirmada) if direcao_confirmada else None

    if letra is None:
        # sem direção confirmada: não envia nada. Voltar para None permite
        # que o mesmo gesto, feito de novo depois, seja enviado na hora.
        ultima_enviada = None
        return

    if direcao_confirmada != ultima_enviada:
        intervalo = INTERVALO_MINIMO_ENVIO
    else:
        intervalo = INTERVALO_REENVIO

    if agora - ultimo_envio < intervalo:
        return  # janela de throttle fechada: tenta de novo no próximo frame

    if enviar_comando(letra):
        ultima_enviada = direcao_confirmada
        ultimo_envio = agora


# ---------------------------------------------------------------------
# Imagens das direções e criação do detector
# ---------------------------------------------------------------------
def carregar_imagens():
    """Carrega as imagens das direções em IMAGENS (avisa as que faltarem)."""
    imagens_faltando = []
    for nome in NOMES_IMAGENS:
        caminho = PASTA_IMAGENS / f"{nome}.jpg"
        imagem = cv2.imread(str(caminho))  # cv2.imread devolve None em silêncio se falhar
        if imagem is None:
            imagens_faltando.append(nome)
        else:
            IMAGENS[nome] = imagem

    if imagens_faltando:
        print("AVISO: não foi possível carregar as imagens das direções:")
        for nome in imagens_faltando:
            print(f"  - {nome}.jpg (procurado em {PASTA_IMAGENS})")
        print("As janelas dessas direções não serão exibidas.")


def criar_detector():
    """Cria o HandLandmarker do MediaPipe (modo VIDEO) ou encerra o programa."""
    if not CAMINHO_MODELO.is_file():
        print("ERRO: modelo do MediaPipe não encontrado.")
        print(f"Esperado em: {CAMINHO_MODELO}")
        print("Baixe 'hand_landmarker.task' (MediaPipe Hand Landmarker) e "
              "coloque nessa pasta.")
        sys.exit(1)

    base_options = python.BaseOptions(model_asset_path=str(CAMINHO_MODELO))
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=2,
        # modo VIDEO: o detector usa o frame anterior como contexto (tracking),
        # em vez de detectar do zero a cada frame -> muito mais estável
        running_mode=vision.RunningMode.VIDEO,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.7,
        min_tracking_confidence=0.7,
    )
    return vision.HandLandmarker.create_from_options(options)


# ---------------------------------------------------------------------
# Classificação dos dedos e da direção
# ---------------------------------------------------------------------
def suavizar_pontos(lado, pontos_novos):
    """Aplica média ponderada entre os pontos novos e os do frame anterior
    da mesma mão, reduzindo tremedeira sem perder responsividade."""
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


def distancia(ponto_a, ponto_b):
    """Distância euclidiana entre dois landmarks normalizados do MediaPipe."""
    return ((ponto_a.x - ponto_b.x) ** 2 + (ponto_a.y - ponto_b.y) ** 2) ** 0.5


def dedo_esticado(mao, dedo, lado):
    """Retorna True se o dedo está esticado.

    Para o polegar a comparação é por DISTÂNCIA AO PULSO (landmark 0), e
    não pelo eixo x: assim a decisão continua correta quando a mão está
    girada na frente da câmera. Esticado = a ponta fica mais longe do
    pulso do que a articulação de referência.
    """
    ponta = mao[dedo["ponta"]]
    articulacao = mao[dedo["articulacao"]]

    if dedo["nome"] == "polegar":
        pulso = mao[0]
        return distancia(ponta, pulso) > distancia(articulacao, pulso)
    else:
        return ponta.y < articulacao.y


def direcao(dedos_d, dedos_e, pontos_d, pontos_e):
    """
    Decide qual direção está sendo indicada.

    Função PURA: apenas retorna o NOME da direção (ou None); o envio
    ao ESP32 é feito por processar_envio() depois da votação confirmar.

    Todas as regras exigem que as duas mãos estejam detectadas ao mesmo tempo:

    - tras:     as duas mãos abertas
    - frente:   as duas mãos fechadas
    - esquerda: mão esquerda fechada e mão direita aberta
    - direita:  mão direita fechada e mão esquerda aberta
    - cima:     polegar E indicador fechados E os outros três dedos
                (médio, anelar e mindinho) esticados nas DUAS mãos,
                com o pulso esquerdo mais alto que o direito
    - baixo:    mesmo gesto de cima, mas com o pulso direito mais alto

    Na imagem, o eixo Y cresce para BAIXO, então o pulso mais alto
    tem o MENOR valor de y (landmark 0 = pulso).
    """
    if dedos_d == [] or dedos_e == [] or pontos_d == [] or pontos_e == []:
        return None

    mao_direita_aberta = all(dedos_d)
    mao_direita_fechada = not any(dedos_d)
    mao_esquerda_aberta = all(dedos_e)
    mao_esquerda_fechada = not any(dedos_e)

    if mao_direita_aberta and mao_esquerda_aberta:
        return "tras"

    if mao_direita_fechada and mao_esquerda_fechada:
        return "frente"

    if mao_esquerda_fechada and mao_direita_aberta:
        return "esquerda"

    if mao_direita_fechada and mao_esquerda_aberta:
        return "direita"

    # Gesto cima/baixo EXATO: nas duas mãos, polegar (índice 0) e indicador
    # (índice 1) fechados E médio (2), anelar (3) e mindinho (4) esticados.
    # Assim, estados mistos (ex.: só um deles fechado) não ativam cima/baixo.
    gesto_cima_baixo = (
        not dedos_d[0] and not dedos_d[1] and dedos_d[2] and dedos_d[3] and dedos_d[4] and
        not dedos_e[0] and not dedos_e[1] and dedos_e[2] and dedos_e[3] and dedos_e[4]
    )

    if gesto_cima_baixo:
        y_pulso_esquerdo = pontos_e[0][1]
        y_pulso_direito = pontos_d[0][1]

        if y_pulso_esquerdo < y_pulso_direito:
            return "cima"
        if y_pulso_direito < y_pulso_esquerdo:
            return "baixo"

    return None


def direcao_estavel(direcao_atual):
    """
    Filtra ruído/flicker: só considera uma direção 'confirmada' se ela
    aparecer com frequência suficiente no histórico recente. Isso evita
    que a janela fique piscando entre direções por causa de um único
    frame com leitura errada.

    Empate: fica com o voto MAIS RECENTE entre os empatados (e não com o
    primeiro que o Counter devolver), o que responde melhor a mudanças
    reais de gesto.
    """
    historico_direcoes.append(direcao_atual)

    contagem = collections.Counter(historico_direcoes)
    max_votos = max(contagem.values())
    candidatos = [d for d, votos in contagem.items() if votos == max_votos]

    if len(candidatos) == 1:
        escolhida = candidatos[0]
    else:
        # percorre do mais recente para o mais antigo e pega o 1º empatado
        escolhida = None
        for voto in reversed(historico_direcoes):
            if voto in candidatos:
                escolhida = voto
                break

    if escolhida is not None and max_votos >= VOTOS_MINIMOS:
        return escolhida

    return None


# ---------------------------------------------------------------------
# Janelas do OpenCV
# ---------------------------------------------------------------------
def janela_existe(nome):
    """True se a janela existe e está visível (protegido contra cv2.error)."""
    try:
        return cv2.getWindowProperty(nome, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


def fechar_janela(nome):
    """Fecha uma janela tolerando que o usuário já a tenha fechado no X."""
    try:
        if janela_existe(nome):
            cv2.destroyWindow(nome)
    except cv2.error:
        pass


def mostrar_direcao(direcao_atual):
    """
    Mostra a janela da imagem correspondente à direção detectada e
    fecha a janela anterior, se for diferente. Se direcao_atual for
    None, fecha qualquer janela de direção que esteja aberta.
    """
    global janela_aberta

    if direcao_atual is None:
        if janela_aberta is not None:
            fechar_janela(janela_aberta)
            janela_aberta = None
        return

    imagem = IMAGENS.get(direcao_atual)
    if imagem is None:
        return

    if janela_aberta is not None and janela_aberta != direcao_atual:
        fechar_janela(janela_aberta)
        janela_aberta = None

    try:
        cv2.imshow(direcao_atual, imagem)
        # posiciona a janela de imagem logo à direita da janela de vídeo
        cv2.moveWindow(direcao_atual, largura_atual + 50, 30)
        janela_aberta = direcao_atual
    except cv2.error:
        # janela fechada pelo usuário no X: apenas esquece que estava aberta
        janela_aberta = None


def exibir_captura(captura):
    """Mostra o frame da câmera. False se o usuário fechou a janela no X."""
    global janela_captura_posicionada

    try:
        cv2.imshow("captura", captura)
        if not janela_captura_posicionada:
            cv2.moveWindow("captura", 0, 30)
            janela_captura_posicionada = True
    except cv2.error:
        return False

    return janela_existe("captura")


# ---------------------------------------------------------------------
# Processamento de um frame
# ---------------------------------------------------------------------
def processar_frame(captura, detector):
    """Detecta as mãos no frame, desenha os pontos e devolve a leitura.

    Retorna (captura, dedos_d, dedos_e, pontos_d, pontos_e), onde cada
    vetor de dedos tem 5 booleanos e cada lista de pontos tem 21 pares
    (x, y) em pixels — vazios quando a mão não foi detectada.
    """
    global largura_atual

    # espelha o frame (como um espelho / câmera selfie): o MediaPipe
    # assume esse tipo de imagem para classificar "Left"/"Right"
    # corretamente
    captura = cv2.flip(captura, 1)
    mp_captura = cv2.cvtColor(captura, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=mp_captura)

    # timestamp monotônico em ms, exigido pelo modo VIDEO (precisa ser
    # sempre crescente). perf_counter_ns não anda para trás se o relógio
    # do sistema for ajustado, diferente de time.time().
    timestamp_ms = time.perf_counter_ns() // 1_000_000
    resultado = detector.detect_for_video(mp_image, timestamp_ms)

    altura, largura, _ = captura.shape
    largura_atual = largura

    pontos_mao_direita = []
    pontos_mao_esquerda = []
    dedos_mao_direita = []
    dedos_mao_esquerda = []
    vistas = {"Right": False, "Left": False}

    for indice_mao, mao in enumerate(resultado.hand_landmarks):
        categoria = resultado.handedness[indice_mao][0]
        lado = categoria.category_name  # "Left" ou "Right"

        # ignora essa mão se o modelo não está confiante sobre qual lado é
        if categoria.score < CONFIANCA_MINIMA_LADO:
            continue

        vistas[lado] = True
        cor = COR_ROXA if lado == "Right" else COR_VERMELHA

        pontos_brutos = []
        for ponto in mao:
            x = int(ponto.x * largura)
            y = int(ponto.y * altura)
            pontos_brutos.append((x, y))

        # suaviza a posição dos pontos antes de desenhar/usar
        pontos_da_mao = suavizar_pontos(lado, pontos_brutos)

        for (x, y) in pontos_da_mao:
            cv2.circle(captura, (x, y), 5, cor, -1)

        estado_dedos = []
        for dedo in DEDOS:
            estado_dedos.append(dedo_esticado(mao, dedo, lado))

        if lado == "Right":
            pontos_mao_direita = pontos_da_mao
            dedos_mao_direita = estado_dedos
        else:
            pontos_mao_esquerda = pontos_da_mao
            dedos_mao_esquerda = estado_dedos

    # mão fora do frame por alguns frames: descarta a suavização antiga
    # (senão os pontos antigos "voam" até a nova posição ao reaparecer)
    for lado, vista in vistas.items():
        if vista:
            ausencias[lado] = 0
        else:
            ausencias[lado] += 1
            if ausencias[lado] >= FRAMES_ATE_RESET:
                pontos_suavizados[lado] = None

    return (captura, dedos_mao_direita, dedos_mao_esquerda,
            pontos_mao_direita, pontos_mao_esquerda)


# ---------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------
def main():
    global janela_aberta

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

    try:
        while True:
            sucesso, captura = camera.read()
            if not sucesso:
                print("Não foi possível capturar a imagem da câmera.")
                break

            (captura, dedos_d, dedos_e,
             pontos_d, pontos_e) = processar_frame(captura, detector)

            if not exibir_captura(captura):
                break  # usuário fechou a janela no X

            direcao_atual = direcao(dedos_d, dedos_e, pontos_d, pontos_e)
            direcao_confirmada = direcao_estavel(direcao_atual)
            mostrar_direcao(direcao_confirmada)

            # único ponto que conversa com o ESP32 (no máx. 1 envio/frame)
            processar_envio(direcao_confirmada, time.monotonic())

            # fecha o programa se 's' for pressionado
            if cv2.waitKey(25) & 0xFF == ord('s'):
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
        janela_aberta = None
        print("Câmera liberada. Programa encerrado.")


if __name__ == "__main__":
    main()
