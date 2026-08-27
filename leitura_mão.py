import cv2
import time
import collections
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# carrega todas as imagens de direção num dicionário
# chave = nome da direção, valor = imagem carregada
IMAGENS = {
    "tras": cv2.imread("./direcoes/tras.jpg"),
    "frente": cv2.imread("./direcoes/frente.jpg"),
    "esquerda": cv2.imread("./direcoes/esquerda.jpg"),
    "direita": cv2.imread("./direcoes/direita.jpg"),
    "cima": cv2.imread("./direcoes/cima.jpg"),
    "baixo": cv2.imread("./direcoes/baixo.jpg"),
}

base_options = python.BaseOptions(
    model_asset_path="hand_landmarker.task"
)
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
detector = vision.HandLandmarker.create_from_options(options)

camera = cv2.VideoCapture(0)

# guarda o nome da janela de direção que está aberta no momento (ou None)
janela_aberta = None

# largura do frame atual da câmera, usada para posicionar a janela de
# imagem à direita da janela de vídeo
largura_atual = 0

# controla se a janela "captura" já foi posicionada na tela
janela_captura_posicionada = False

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
ALPHA_SUAVIZACAO = 0.4  # peso do frame atual (0 = ignora o novo, 1 = sem suavização)
pontos_suavizados = {"Right": None, "Left": None}

# --- estabilização da direção exibida (filtro de voto majoritário) ---
HISTORICO_TAMANHO = 7
VOTOS_MINIMOS = 4  # precisa aparecer pelo menos essa quantidade de vezes no histórico
historico_direcoes = collections.deque(maxlen=HISTORICO_TAMANHO)


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


def dedo_esticado(mao, dedo, lado):
    """Retorna True se o dedo está esticado."""
    ponta = mao[dedo["ponta"]]
    articulacao = mao[dedo["articulacao"]]

    if dedo["nome"] == "polegar":
        if lado == "Right":
            return ponta.x > articulacao.x
        else:
            return ponta.x < articulacao.x
    else:
        return ponta.y < articulacao.y


def direcao(dedos_d, dedos_e, pontos_d, pontos_e):
    """
    Decide qual direção está sendo indicada. Todas as regras exigem
    que as duas mãos estejam detectadas ao mesmo tempo.

    - tras:     as duas mãos abertas
    - frente:   as duas mãos fechadas
    - esquerda: mão esquerda fechada e mão direita aberta
    - direita:  mão direita fechada e mão esquerda aberta
    - cima:     polegar e indicador fechados nas duas mãos,
                com a mão esquerda acima da direita
    - baixo:    polegar e indicador fechados nas duas mãos,
                com a mão direita acima da esquerda
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

    polegar_e_indicador_fechados = (
        not dedos_d[0] and not dedos_d[1] and
        not dedos_e[0] and not dedos_e[1]
    )

    if polegar_e_indicador_fechados:
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
    """
    historico_direcoes.append(direcao_atual)

    contagem = collections.Counter(historico_direcoes)
    direcao_mais_comum, votos = contagem.most_common(1)[0]

    if direcao_mais_comum is not None and votos >= VOTOS_MINIMOS:
        return direcao_mais_comum

    return None


def mostrar_direcao(direcao_atual):
    """
    Mostra a janela da imagem correspondente à direção detectada e
    fecha a janela anterior, se for diferente. Se direcao_atual for
    None, fecha qualquer janela de direção que esteja aberta.
    """
    global janela_aberta, largura_atual

    if direcao_atual is None:
        if janela_aberta is not None:
            cv2.destroyWindow(janela_aberta)
            janela_aberta = None
        return

    imagem = IMAGENS.get(direcao_atual)
    if imagem is None:
        print(f"Aviso: imagem para '{direcao_atual}' não foi encontrada.")
        return

    if janela_aberta is not None and janela_aberta != direcao_atual:
        cv2.destroyWindow(janela_aberta)

    cv2.imshow(direcao_atual, imagem)
    # posiciona a janela de imagem logo à direita da janela de vídeo
    cv2.moveWindow(direcao_atual, largura_atual + 50, 30)
    janela_aberta = direcao_atual


if camera.isOpened() == False:
    print("não tem camera")

while camera.isOpened():
    sucesso, captura = camera.read()

    if not sucesso:
        print("Não foi possível capturar a imagem da câmera.")
        break

    # espelha o frame (como um espelho / câmera selfie): o MediaPipe
    # assume esse tipo de imagem para classificar "Left"/"Right"
    # corretamente
    captura = cv2.flip(captura, 1)

    mp_captura = cv2.cvtColor(captura, cv2.COLOR_BGR2RGB)

    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=mp_captura
    )

    # timestamp em milissegundos, exigido pelo modo VIDEO (precisa ser
    # sempre crescente entre chamadas)
    timestamp_ms = int(time.time() * 1000)
    resultado = detector.detect_for_video(mp_image, timestamp_ms)

    altura, largura, _ = captura.shape
    largura_atual = largura

    pontos_mao_direita = []
    pontos_mao_esquerda = []
    dedos_mao_direita = []
    dedos_mao_esquerda = []

    for indice_mao, mao in enumerate(resultado.hand_landmarks):
        categoria = resultado.handedness[indice_mao][0]
        lado = categoria.category_name  # "Left" ou "Right"

        # ignora essa mão se o modelo não está confiante sobre qual lado é
        if categoria.score < CONFIANCA_MINIMA_LADO:
            continue

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

    cv2.imshow("captura", captura)
    if not janela_captura_posicionada:
        cv2.moveWindow("captura", 0, 30)
        janela_captura_posicionada = True

    direcao_atual = direcao(
        dedos_mao_direita, dedos_mao_esquerda,
        pontos_mao_direita, pontos_mao_esquerda
    )
    direcao_confirmada = direcao_estavel(direcao_atual)
    mostrar_direcao(direcao_confirmada)

    # fecha a janela se 's' for pressionado
    if cv2.waitKey(25) & 0xFF == ord('s'):
        break

camera.release()

# fecha todos os frames
cv2.destroyAllWindows()
