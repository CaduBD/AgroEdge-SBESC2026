# AgroEdge - dados da área onde a placa está instalada. Edite na instalação.
# O modelo foi treinado com TAW de 25 a 140 mm; fora disso a resposta não é confiável.

import time

# água que o solo segura e a planta consegue usar (θCC − θPMP, em m³/m³)
# arenoso ~0,06-0,09 | franco-arenoso ~0,11 | argiloso ou Vertissolo ~0,15-0,18
AGUA_DISP = 0.11

# profundidade efetiva das raízes (m); com gotejamento, de 0,4 a 0,8
RAIZ_M = 0.6

# data da última poda; atualize a cada poda
# FORMATO DAS DATAS neste arquivo: (ano, mês, dia), com parênteses e vírgulas, nessa ordem
# (ao contrário do dd/mm/aaaa), números sem zero à esquerda e sem aspas.
#   15 de janeiro de 2026  ->  (2026, 1, 15)
#   20 de novembro de 2026 ->  (2026, 11, 20)
# Errado: "15/01/2026", (15, 1, 2026), (2026, 01, 15)
DATA_PODA = (2026, 1, 15)

# irrigação (usados por lamina.py). ASSUMIDO: conferir no sistema instalado
EFICIENCIA = 0.9     # fração da água do gotejamento que chega à raiz
AREA_M2 = 7.0        # área de cada planta (espaçamento 3,5 m × 2,0 m)
VAZAO_L_H = 8.0      # vazão dos gotejadores de uma planta, em litros por hora

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
# acertado (o ET0 precisa do dia do ano). Mesmo formato da DATA_PODA: (ano, mês, dia).
#   ligar em 20 de novembro de 2026 -> DATA_INSTALACAO = (2026, 11, 20)
# None = não informada (aí o modo "24h" só funciona com o DS3231 ou o Wi-Fi acertando a hora)
DATA_INSTALACAO = None


def taw():
    """Água total disponível no solo, em mm (FAO-56, eq. 82)."""
    return 1000 * AGUA_DISP * RAIZ_M


def dap(hoje):
    """Dias após a poda. hoje = (ano, mês, dia). O modelo foi treinado com DAP de 0 a 108."""
    a = time.mktime(DATA_PODA + (0, 0, 0, 0, 0, 0))
    b = time.mktime(tuple(hoje) + (0, 0, 0, 0, 0, 0))
    return int((b - a) // 86400)


# fração do TAW que a uva gasta sem sofrer (FAO-56, tab. 22). ASSUMIDO: conferir com o Prof. Max
P_DEPLECAO = 0.35


def kc(d):
    """Kc da uva Itália pelo DAP (Ávila Netto et al., 2000)."""
    return -8e-5 * d * d + 0.0089 * d + 0.488
