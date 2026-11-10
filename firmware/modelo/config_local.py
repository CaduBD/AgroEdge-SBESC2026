# AgroEdge - dados da área onde a placa está instalada. Edite na instalação.
# Aqui fica só o que é DO LOCAL (cultura plantada, datas, solo, irrigação, sensores).
# Os dados científicos de cada cultura (Kc, p, raiz) ficam em culturas.py.
# O modelo foi treinado com TAW de 25 a 140 mm; fora disso a resposta não é confiável.

import culturas

# ---------------------------------------------------------------- cultura e ciclo
# cultura plantada: um dos nomes de culturas.CULTURAS
#   "uva_italia"          uva de mesa cv. Itália (dias contados a partir da poda)
#   "manga_tommy_atkins"  manga cv. Tommy Atkins (dias contados a partir da floração)
CULTURA = "uva_italia"

# data do evento que inicia o ciclo da cultura escolhida: a PODA para a uva, o INÍCIO DA
# FLORAÇÃO para a manga (ver "referencia" em culturas.py). Atualize a cada novo ciclo.
# FORMATO DAS DATAS neste arquivo: (ano, mês, dia), com parênteses e vírgulas, nessa ordem
# (ao contrário do dd/mm/aaaa), números sem zero à esquerda e sem aspas.
#   15 de janeiro de 2026  ->  (2026, 1, 15)
#   20 de novembro de 2026 ->  (2026, 11, 20)
# Errado: "15/01/2026", (15, 1, 2026), (2026, 01, 15)
DATA_REFERENCIA = (2026, 1, 15)

# ---------------------------------------------------------------- solo
# água que o solo segura e a planta consegue usar (θCC − θPMP, em m³/m³; FAO-56, tab. 19).
# θCC = umidade na capacidade de campo, θPMP = no ponto de murcha permanente.
# arenoso ~0,06-0,09 | franco-arenoso ~0,11 | argiloso ou Vertissolo ~0,15-0,18
# ASSUMIDO: 0,11 (franco-arenoso); o ideal é a análise de solo do pomar
AGUA_DISP = 0.11

# profundidade efetiva das raízes (m). None = usa o valor da cultura (culturas.py);
# preencha só se houver medida no pomar (ex.: trincheira ou recomendação do agrônomo)
RAIZ_M = None

# fração de depleção p (FAO-56, tab. 22). None = usa o valor da cultura (culturas.py)
P_LOCAL = None

# ---------------------------------------------------------------- irrigação
# usados por lamina.py para transformar a lâmina (mm) em tempo de válvula aberta.
# ASSUMIDO: valores de um parreiral; trocar pelos do sistema instalado.
# EFICIENCIA: fração da água aplicada que chega à raiz (gotejamento e microaspersão: 0,70 a
#   0,95, segundo Pinto, Silva e Coelho/Embrapa; aspersão: 0,50 a 0,75)
# AREA_M2: área de cada planta = espaçamento entre linhas × entre plantas
#   (uva 3,5 × 2,0 m = 7 m²; manga típica 8 × 5 m = 40 m²)
# VAZAO_L_H: soma da vazão dos emissores (gotejadores ou microaspersores) de UMA planta, em L/h
EFICIENCIA = 0.9
AREA_M2 = 7.0
VAZAO_L_H = 8.0

# pluviômetro de báscula (usados por pluviometro.py)
# GPIO livre no conector de expansão da BitDogLab; o outro fio do sensor vai no GND
PINO_PLUVIOMETRO = 16
# mm de chuva por virada da báscula. ASSUMIDO: 0,2794 mm é o valor de fábrica dos modelos
# Misol/Fine Offset; calibrar com água medida (ver pluviometro.py) e trocar aqui
MM_POR_PULSO = 0.2794

# anemômetro de conchas Met One 014A (usados por anemometro.py)
# GPIO livre no conector de expansão, ao lado do GP16 do pluviômetro; o outro fio vai no GND
PINO_ANEMOMETRO = 17
# calibração de fábrica do 014A: v (m/s) = ANEMO_M × f (Hz) + ANEMO_B; com f = 0 dá 0
ANEMO_M = 0.8
ANEMO_B = 0.447
# altura das conchas acima do solo (m); o ET0 do FAO-56 usa vento a 2 m, e o anemometro.py
# converte se for outra altura. ASSUMIDO: 2,0 m; medir na instalação e trocar aqui
ANEMO_ALTURA_M = 2.0
# pulsos mais próximos que isso são repique da reed (a 45 m/s os pulsos vêm a cada ~18 ms).
# ASSUMIDO: 2 ms; conferir no MODO 3 do teste_anemometro.py
ANEMO_DEBOUNCE_MS = 2


# piranômetro SN-300AL-RA-N01 por RS-485 / Modbus-RTU (usados por piranometro.py)
# MAX485: DI no TX, RO no RX (com divisor 1k/2k), DE+RE juntos no pino de direção
PINO_RS485_TX = 8      # UART1 TX
PINO_RS485_RX = 9      # UART1 RX
PINO_RS485_DE_RE = 4
# valores que funcionaram no teste de bancada; se trocar o sensor, rode o scan
# (bancada/teste_piranometro_rs485.py com SCAN_MODE = True)
PIRANO_ENDERECO = 1
PIRANO_BAUD = 4800

# DHT22 (temperatura e umidade do ar; usados por termohigro.py)
# conector IDC, fileira "GP18 GP19 GP20 GP4 GP9 GP8 5V": GP18 é o 1º pino
PINO_DHT22 = 18

# relógio DS3231 no I²C0 (usados por relogio.py); opcional se houver Wi-Fi
PINO_I2C0_SDA = 0
PINO_I2C0_SCL = 1
FUSO_HORAS = -3        # hora local de Petrolina (UTC-3)
# Wi-Fi para acertar a hora pela internet (NTP). Vazio = não usa Wi-Fi
WIFI_SSID = ""
WIFI_SENHA = ""

# local da estação, para o ET0 (usados por main.py e eto.py). ASSUMIDO: Petrolina;
# trocar pela posição do pomar (GPS do celular serve)
LATITUDE = -9.39       # graus, sul negativo
ALTITUDE_M = 370

# irrigação aplicada: "arquivo" = soma o que for registrado com main.registrar_irrigacao(mm);
# "zero" = considera que não houve irrigação
IRRIGACAO_MODO = "arquivo"

# quando o dia fecha (usado por main.py):
#   "meia_noite" = dia do calendário (uso normal; precisa do relógio acertado)
#   "24h"        = modo de teste: fecha 24 h de funcionamento depois de ligar (não precisa de relógio)
MODO_FECHAMENTO = "meia_noite"
# data do dia em que a placa for ligada no campo, usada no modo "24h" se o relógio não estiver
# acertado (o ET0 precisa do dia do ano). Mesmo formato da DATA_REFERENCIA: (ano, mês, dia).
#   ligar em 20 de novembro de 2026 -> DATA_INSTALACAO = (2026, 11, 20)
# None = não informada (aí o modo "24h" só funciona com o DS3231 ou o Wi-Fi acertando a hora)
DATA_INSTALACAO = None


# ---------------------------------------------------------------- valores derivados
# (não editar: saem da cultura escolhida e dos valores acima)
_c = culturas.cultura(CULTURA)
RAIZ_EFETIVA_M = RAIZ_M if RAIZ_M is not None else _c["raiz_m"]
P_DEPLECAO = P_LOCAL if P_LOCAL is not None else _c["p"]


def taw():
    """Água total disponível no solo, em mm (FAO-56, eq. 82): TAW = 1000 × (θCC − θPMP) × Zr."""
    return 1000 * AGUA_DISP * RAIZ_EFETIVA_M


def dap(hoje):
    """Dias do ciclo: dias desde DATA_REFERENCIA (poda ou floração). hoje = (ano, mês, dia).
    O nome "dap" vem da uva (dias após a poda) e é o que o classificador recebe; ele foi
    treinado com 0 a 108."""
    return culturas.dias_desde(DATA_REFERENCIA, tuple(hoje))


def kc(d):
    """Kc da cultura escolhida no dia d do ciclo (culturas.py)."""
    return culturas.kc_do_dia(CULTURA, d)[0]
