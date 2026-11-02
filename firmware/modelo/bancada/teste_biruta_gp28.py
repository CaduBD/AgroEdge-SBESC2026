# AgroEdge - teste de BANCADA da biruta no GP28 (ADC2) da BitDogLab v6.3, sem ADS1115.
# MicroPython. Arquivo único: não precisa do biruta.py. Testado em 31/10/2026.
#
# Antes: no verso da placa, passe o jumper J1 da posição 1-2 (microfone) para 2-3
# (GP28 no conector IDC). Para usar o microfone de novo, volte para 1-2.
#
# Ligação (conector IDC, fileira com "GND GP16 GP17 GND GP28 3V3 GND" na serigrafia,
# contando os pinos da esquerda para a direita):
#
#   3V3 (6º) ──[10 kΩ]──┬── GP28 (5º)
#                       │
#                 fio VERDE da biruta
#                 fio PRETO da biruta ── GND (7º)
#
# MODO 0 (fileira): confere se você está na fileira certa do IDC e se o GP28 está livre.
#   Ligue SÓ o resistor de 10 kΩ entre o 5º e o 6º pino (contando da esquerda) da fileira
#   que você acha que é a do GP28/3V3. Nada de biruta ainda.
# MODO 1 (leitura): mostra tensão, resistência e direção, e acende na matriz de LEDs o
#   ponto da borda que corresponde à direção (N em cima, sentido horário).
# MODO 2 (calibração): aponte a seta para cada uma das 16 posições, aperte o botão A em
#   cada uma, e no fim ele imprime a R_TAB da sua peça para colar aqui embaixo.

import math
import time
from machine import ADC, Pin

MODO = 0

R_PULLUP = 10000.0
OFFSET_GRAUS = 0.0          # correção se a marca N não estiver apontada para o norte real

# Referência SparkFun (mesmo fabricante). Troque pela medida no MODO 2.
R_TAB = [33000, 6570, 8200, 891, 1000, 688, 2200, 1410,
         3900, 3140, 16000, 14120, 120000, 42120, 64900, 21880]
NOMES = ["N", "NNE", "NE", "ENE", "L", "ESE", "SE", "SSE",
         "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]

adc = ADC(28)
botao_a = Pin(5, Pin.IN, Pin.PULL_UP)

# ---------------------------------------------------------------- matriz de LEDs 5x5
# Índice do LED em cada (linha, coluna), linha 0 = em cima. Mapa usado nos exemplos da
# BitDogLab. Se a varredura do início não andar no sentido horário a partir do meio de
# cima, troque INVERTER_X para True.
MAPA = [[24, 23, 22, 21, 20],
        [15, 16, 17, 18, 19],
        [14, 13, 12, 11, 10],
        [5, 6, 7, 8, 9],
        [4, 3, 2, 1, 0]]
INVERTER_X = False
# 16 LEDs da borda, um por direção, começando em N (meio de cima) e indo no sentido horário
ANEL = [(0, 2), (0, 3), (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (4, 3),
        (4, 2), (4, 1), (4, 0), (3, 0), (2, 0), (1, 0), (0, 0), (0, 1)]

try:
    from neopixel import NeoPixel
    matriz = NeoPixel(Pin(7), 25)
except Exception:
    matriz = None


def led(linha, coluna):
    if INVERTER_X:
        coluna = 4 - coluna
    return MAPA[linha][coluna]


def mostrar(direcao=None, cor=(0, 0, 25)):
    if matriz is None:
        return
    for i in range(25):
        matriz[i] = (0, 0, 0)
    matriz[led(2, 2)] = (4, 4, 4)                 # centro aceso fraco, como referência
    if direcao is not None:
        matriz[led(*ANEL[direcao])] = cor
    matriz.write()


def varrer_anel():
    for i in range(16):
        mostrar(i, (0, 20, 0))
        time.sleep_ms(60)
    mostrar()


# ---------------------------------------------------------------- leitura
def amostrar(n=64):
    """Média e desvio da leitura do ADC, como fração de 3V3 (0 a 1)."""
    s = s2 = 0
    for _ in range(n):
        v = adc.read_u16()
        s += v
        s2 += v * v
    media = s / n
    desvio = math.sqrt(max(0, s2 / n - media * media))
    return media / 65535, desvio / 65535


R_MAX = 250000.0           # a maior posição da biruta é ~120 kΩ; acima disso é fio solto


def resistencia(f):
    # Na BitDogLab o GP28 com só o pull-up lê ~3,20 V, e não 3,30 V. Por isso o "aberto"
    # é decidido pela resistência calculada, não por uma tensão fixa.
    if f <= 0.03:
        return 0.0           # curto
    if f >= 0.999:
        return None          # aberto
    r = R_PULLUP * f / (1.0 - f)
    return None if r > R_MAX else r


def classificar(r):
    """Posição mais próxima na escala log e folga até a segunda (quanto maior, mais certeza)."""
    lr = math.log(r)
    d = sorted((abs(lr - math.log(rt)), i) for i, rt in enumerate(R_TAB))
    folga = d[1][0] - d[0][0]
    return d[0][1], folga


# ---------------------------------------------------------------- modos
def modo_fileira():
    print("Só o resistor de 10 kΩ entre o 5º e o 6º pino da fileira escolhida.\n")
    # Se a fileira for a outra (GP18 GP19 GP20 GP4 GP9 GP8 5V), o 5º e o 6º pino são GP9 e GP8.
    gp8 = Pin(8, Pin.OUT, value=1)
    gp9 = Pin(9, Pin.IN, Pin.PULL_DOWN)
    time.sleep_ms(20)
    outra_fileira = gp9.value() == 1
    Pin(8, Pin.IN)                                 # solta o GP8 de novo
    Pin(9, Pin.IN)
    f, ruido = amostrar(256)
    v = f * 3.3
    if outra_fileira:
        print("Você está na OUTRA fileira (GP18 ... GP9 GP8 5V). Passe para a fileira do GP28.")
        print("Cuidado: na ponta direita dessa fileira está o 5 V. Nunca ligue nada nele.")
    elif v > 2.9:
        print("Fileira certa e GP28 livre: o resistor puxou o GP28 para %.2f V." % v)
        print("O 5º pino é o GP28, o 6º é o 3V3 e o 7º (ponta direita) é GND.")
        print("Pode ligar a biruta e passar para o MODO 1.")
    elif 1.2 < v < 2.1:
        print("GP28 preso em %.2f V (ruído %.3f V)." % (v, ruido * 3.3))
        print("Ou o resistor não está entre GP28 e 3V3, ou o microfone está segurando o GP28.")
        print("Confira se o jumper J1 (verso da placa) está na posição 2-3, e não 1-2.")
    else:
        print("GP28 em %.2f V: o resistor não parece estar entre GP28 e 3V3. Confira os pinos." % v)


def modo_leitura():
    print("Varredura da matriz: deve andar no sentido horário a partir do meio de cima.")
    varrer_anel()
    print("Gire a seta. Ctrl+C para parar.\n")
    print("  tensão   resistência   direção        folga  observação")
    while True:
        f, ruido = amostrar()
        r = resistencia(f)
        obs = ""
        if ruido * 3.3 > 0.03:
            obs = "leitura ruidosa: J1 em 1-2 (microfone) ou mau contato"
        if r is None:
            print("  %.3f V   ABERTO        —                     fio solto ou par errado (é verde e preto)" % (f * 3.3))
            mostrar(None)
        elif r == 0.0:
            print("  %.3f V   CURTO         —                     fio da biruta encostado no GND?" % (f * 3.3))
            mostrar(None)
        else:
            i, folga = classificar(r)
            graus = (i * 22.5 + OFFSET_GRAUS) % 360
            if folga < 0.03 and not obs:
                obs = "no limite entre duas posições (normal durante o giro)"
            print("  %.3f V   %8.0f Ω    %-3s %5.1f°     %.2f   %s" % (f * 3.3, r, NOMES[i], graus, folga, obs))
            mostrar(i, (25, 8, 0) if obs else (0, 0, 25))
        time.sleep_ms(400)


def modo_calibracao():
    medidas = []
    print("Comece com a seta apontando para a marca N da biruta e vá no sentido horário.")
    print("As posições intermediárias (NNE, ENE...) são estreitas: fica no meio entre duas")
    print("principais. Gire devagar até a leitura ao vivo mudar de valor e só então aperte A.\n")
    for i, nome in enumerate(NOMES):
        mostrar(i, (25, 25, 0))
        print("Aponte a seta para %-3s (LED amarelo) e aperte o botão A..." % nome)
        ultimo = None
        while botao_a.value():
            # leitura ao vivo: imprime só quando a resistência muda mais de 3%
            f, _ = amostrar(32)
            r_vivo = resistencia(f)
            if r_vivo != ultimo and (r_vivo is None or not ultimo
                                     or abs(r_vivo - ultimo) / ultimo > 0.03):
                print("      agora: %s" % ("ABERTO" if r_vivo is None else "%.0f Ω" % r_vivo))
                ultimo = r_vivo
            time.sleep_ms(80)
        f, ruido = amostrar(256)
        r = resistencia(f)
        medidas.append(r)
        print("   %-3s  %.3f V  %s" % (nome, f * 3.3, "ABERTO" if r is None else "%.0f Ω" % r))
        while not botao_a.value():
            time.sleep_ms(20)
        time.sleep_ms(250)
    mostrar()
    print("\nCole no topo deste arquivo:")
    print("R_TAB = [" + ", ".join("%.0f" % (m or 0) for m in medidas) + "]")
    validas = sorted(m for m in medidas if m)
    for a, b in zip(validas, validas[1:]):
        if b / a < 1.08:
            print("Atenção: %.0f e %.0f Ω ficaram a menos de 8%% um do outro." % (a, b))
    if len(validas) < 16:
        print("Atenção: alguma posição deu ABERTO. Confira o contato e repita.")


if MODO == 0:
    modo_fileira()
elif MODO == 1:
    modo_leitura()
else:
    modo_calibracao()
