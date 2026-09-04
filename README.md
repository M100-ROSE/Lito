<h1 align="center">Lito
  <br>
  <br>
  "Saudações Aeronáuticas!" 
  <br>
  -Lito Sousa
  
</h1>

<div align="center">
  
| nome | numero | github |
|:------:|:------:|:------:|
|Kaike |   18   | [M1000](https://github.com/M100-ROSE)|
|Maria |  00 | [EDDY](https://github.com/limasantosmaria2112-art)
|Marcos| 00 | [KIELOP](https://github.com/oliveiramarcos16-eng)

</div>
<h2 align="center">SOBRE</h2>

**O Lito é um projeto em homenagem ao Lito Sousa**. Feita por alunos do 1ºDSB para a feira de ciências do Colégio Kennedy, é um drone montado completamente do zero usando um esp wroom32. Para movê-lo usamos um software em Python que usando [mediapipe](https://github.com/google-ai-edge/mediapipe) e [opencv](https://github.com/opencv/opencv) lê suas mãos e dependendo da posição delas ele executa um comando, dentre eles temos, **cima, baixo, frente, trás, esquerda, direita e rotacionar no próprio eixo em sentido horário ou anti-horário** (que será adicionado posteriormente). Aqui listaremos todos os componentes necessários para montar seu próprio Lito, e também todo o diagrama de ligação dos componentes. Após o termino do projeto deixaremos anexados vídeos de seu funcionamento.

<h2 align="center">COMPONENTES</h2>

<div align="center">
  
| nome | quantidadde |
|:------:|:------:|
|esp-32D  |1|
|motor 8520 mini coreless  cw|  2 |
|motor 8520 mini coreless ccw| 2 |
|sensor de distancia a laser GY-530 VL53L0X | 5|
|transistor IRLB4132 | 4|
|bateria lipo 3,7v 500mah|1|
|kit 127 tubos termo retráteis|1|
|placa de carregamento bateria lipo|1|
|giroscópio e acelerómetro MPU6050|1|
|resistores metalicos 1/4w| 8|
|un cabeçalho de pino de furo redondo|40|
|fio 24AWG para negativo| 1|
|fio 24AWG para positivo| 1|
|fio 30AWG para positivo|1|
|fio 30AWG para negativo|1|
|jst ph 2.0mm 2pinos macho femea|3|
> (os fios devem ser de cores diferentes para ajudar na identificação e vc deve comprar mais um cabo jst ph 2.00m macho e femea caso sua bateria não venha com  )

</div>


<h2>Guia Completo do Projeto – Lito</h2>
<h2>1. Sistema de Alimentação</h2>

<h3>1.1 Bateria LiPo 3,7 V 500 mAh</h3>

- **Função:** Fonte principal de energia do drone.
- **Onde fica:** Fixada no centro ou parte de baixo do quadro (para manter o centro de gravidade baixo).
- **Ligação:** Positivo (vermelho) e negativo (preto) através de conector JST PH 2.0.
  
<h3>1.2 Regulador de Tensão 3,3 V (LDO)</h3>

- **Função:** Transforma a tensão da bateria (3,7~4,2 V) em 3,3 V estáveis e limpos.
- **Por que é necessário:** O ESP32-WROOM-32 e todos os sensores só funcionam corretamente com 3,3 V.
- **Onde fica:** Entre a bateria e o ESP32.
- **Ligação:**
  - `Vin` → Positivo da bateria
  - `Vout` → Linha de 3,3 V do projeto
  - `GND` → Negativo da bateria
- **Modelos recomendados:** AP2112K-3.3 ou HT7333

<h3>1.3 Capacitores</h3>

| Capacitor              | Quantidade | Função                              | Onde colocar                              |
|:----------------------:|:----------:|:-----------------------------------:|:-----------------------------------------:|
| 10 µF ou 22 µF         | 2          | Filtragem do regulador              | Entrada e saída do regulador              |
| 100 nF (0,1 µF)        | 8 a 10     | Desacoplamento (reduz ruído)        | Perto do ESP32, MPU6050 e cada VL53L0X    |
| 100 µF ou 220 µF       | 1          | Reservatório de energia             | Direto na linha da bateria                |

- **Siglas:**
  - µF = Microfarad
  - nF = Nanofarad


<h2> 2. Controlador de Voo (Cérebro do Drone)</h2>

<h3>2.1 ESP32-WROOM-32</h3>

- **Função:** É o cérebro do drone. Processa os dados dos sensores, calcula a correção de estabilidade (PID) e gera os sinais PWM para os motores. Também permite controle via bluetooth.
- **Onde fica:** No centro do quadro, bem fixo e nivelado.
- **Alimentação:** entre 3,5 e 4,1 da bateria

---

<h2>3. Sensores</h2>

<h3>3.1 MPU6050 (Giroscópio + Acelerômetro)</h3>

- **Função:** Mede a inclinação e a rotação do drone em todos os eixos. Essencial para o controle de estabilidade.
- **Onde fica:** Bem no centro do quadro, abaixo do esp32.

---

<h3>3.2 GY-530 VL53L0X (Sensor de Distância a Laser) – 5 unidades</h3>

- **Função:** Mede a distância até o solo ou obstáculos com precisão (sensor ToF). Usado principalmente para controle de distancia de obstaculos.
- **Onde ficam:** Um apontando para baixo(distancia do solo) os outros 4 cada um apontando  para esquerda, direita, frente e trás.
---

<h2>4. Sistema de Propulsão (Motores)</h2>

<h3> 4.1 Motores Coreless 8025 (2 CW + 2 CCW)</h3>

- **Função:** Geram a sustentação (empuxo) do drone.
- **Onde ficam:** Um em cada braço do quadro.
- **Sentido de rotação recomendado:**
  - Frente Direita → CCW
  - Frente Esquerda → CW
  - Trás Direita → CW
  - Trás Esquerda → CCW
 
---

### 4.2 MOSFETs IRLB4132 (1 por motor)

- **Função:** Funcionam como “chaves eletrônicas” que ligam e desligam os motores rapidamente (controle por PWM).
- **Onde ficam:** Perto de cada motor ou em uma placa central.
- **Ligação de cada MOSFET:**
  - `Drain` → Fio negativo do motor
  - `Source` → GND
  - `Gate` → Resistor de 100~220 Ω → Pino PWM do ESP32
- **Sigla:** MOSFET = *Metal-Oxide-Semiconductor Field-Effect Transistor*

### 4.3 Diodos 1N4148 (1 por motor)

- **Função:** Protegem o circuito contra picos de tensão gerados pelos motores (back-EMF).
- **Onde ficam:** Em paralelo com cada motor (cátodo no positivo do motor).

### 4.4 Resistores

- **100~220 Ω (4 unidades):** Limitam a corrente no Gate do MOSFET.
- **10 kΩ (4 unidades):** Pull-down – garantem que o motor fique desligado quando o ESP32 está desligado ou reiniciando.

---

## 5. Conexões de Sinais (Resumo)

| Função                    | Pino do ESP32 | Componente ligado            |
|---------------------------|---------------|------------------------------|
| I2C SDA                   | GPIO 21       | MPU6050 + 5x VL53L0X         |
| I2C SCL                   | GPIO 22       | MPU6050 + 5x VL53L0X         |
| Motor 1 (Frente Direita)  | GPIO 25       | Gate do MOSFET 1             |
| Motor 2 (Trás Direita)    | GPIO 26       | Gate do MOSFET 2             |
| Motor 3 (Trás Esquerda)   | GPIO 33       | Gate do MOSFET 3             |
| Motor 4 (Frente Esquerda) | GPIO 32       | Gate do MOSFET 4             |

---

## 6. Fluxo de Energia (Resumo Visual)

```text
Bateria LiPo (3,7~4,2 V)
        │
        ├──→ Capacitor 100/220 µF
        │
        ├──→ Entrada do Regulador 3,3 V
        │         │
        │         ├──→ Capacitor 10/22 µF (entrada)
        │         │
        │         └──→ Saída 3,3 V
        │                   │
        │                   ├──→ Capacitor 10/22 µF (saída)
        │                   │
        │                   ├──→ ESP32 (3V3) + Capacitor 100 nF
        │                   ├──→ MPU6050 + Capacitor 100 nF
        │                   └──→ 5x VL53L0X + 5x Capacitor 100 nF
        │
        └──→ Motores (alimentação direta, sem passar pelo regulador)
```

---

## 7. Significado das Principais Siglas do Projeto

| Sigla     | Significado Completo                                      | Explicação Simples                              |
|-----------|-----------------------------------------------------------|-------------------------------------------------|
| ESP32     | Espressif Systems 32-bit                                  | Microcontrolador principal                      |
| LiPo      | Lithium Polymer                                           | Tipo de bateria                                 |
| LDO       | Low Dropout Regulator                                     | Regulador de tensão eficiente                   |
| MPU6050   | Motion Processing Unit 6050                               | Giroscópio + Acelerômetro                       |
| VL53L0X   | Sensor de distância a laser                               | Sensor ToF                                      |
| ToF       | Time of Flight                                            | Mede distância pelo tempo da luz                |
| MOSFET    | Metal-Oxide-Semiconductor Field-Effect Transistor         | Transistor de potência                          |
| CW / CCW  | Clockwise / Counter-Clockwise                             | Sentido de rotação das hélices                  |
| PWM       | Pulse Width Modulation                                    | Controle de velocidade dos motores              |
| I2C       | Inter-Integrated Circuit                                  | Protocolo de comunicação dos sensores           |
| GPIO      | General Purpose Input/Output                              | Pinos digitais do ESP32                         |
| GND       | Ground                                                    | Terra / negativo comum                          |
| VCC / 3V3 | Voltage Common Collector / 3.3 Volt                       | Alimentação positiva                            |
| Vin       | Voltage Input                                             | Entrada de tensão do regulador                  |
| Vout      | Voltage Output                                            | Saída de tensão do regulador                    |

---

## 8. Observações Finais

- Sempre teste os motores **sem hélices** primeiro.
- Use tubo termo retrátil em todas as soldas.
- Mantenha os fios de potência (24 AWG) o mais curtos possível.
- O sensor VL53L0X principal deve apontar para baixo (controle de altura).
- Calibre o MPU6050 com o drone em superfície plana antes do primeiro voo.

---

**Documento gerado para o projeto de Mini Drone com ESP32-WROOM-32**

