# AgroEdge - dados da área onde a placa está instalada. Edite na instalação.
# O modelo foi treinado com TAW de 25 a 140 mm; fora disso a resposta não é confiável.

import time

# água que o solo segura e a planta consegue usar (θCC − θPMP, em m³/m³)
# arenoso ~0,06-0,09 | franco-arenoso ~0,11 | argiloso ou Vertissolo ~0,15-0,18
AGUA_DISP = 0.11

# profundidade efetiva das raízes (m); com gotejamento, de 0,4 a 0,8
RAIZ_M = 0.6

# data da última poda (ano, mês, dia); atualize a cada poda
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
