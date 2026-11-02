# AgroEdge - driver da biruta (sensor de direção do vento, família Fine Offset / Misol).
# MicroPython (BitDogLab / RP2040). Versão oficial do projeto: leitura pelo ADS1115.
#
# A biruta é um resistor variável: 8 chaves reed + resistores, e o ímã da seta fecha uma
# chave (ou duas, nas posições intermediárias) -> 16 resistências, de 22,5° em 22,5°.
# Ligada em divisor de tensão com um resistor fixo de 10 kΩ para o 3V3, vira uma tensão.
#
# Ligação oficial:
#   3V3 ──[10 kΩ]──┬── ADS1115 A1
#                  │
#            fio VERDE da biruta
#            fio PRETO da biruta ── GND
#   Opcional (recomendado): ADS1115 A3 ligado direto no 3V3 -> leitura ratiométrica, que
#   não depende do valor exato do trilho de 3,3 V.
#
# Uso:
#   import biruta
#   b = biruta.criar_padrao()                  # ADS1115 0x48 no I²C0 (GPIO0/GPIO1), biruta no A1
#   i, graus, nome, r = b.ler()                # ex.: (2, 45.0, "NE", 8190.0)
#
# Alternativa de bancada, sem ADS1115: Biruta(gpio_adc=28), com o jumper J1 (verso da placa)
# na posição 2-3. Ver bancada/teste_biruta_gp28.py.
#
# Direção é DE ONDE o vento vem (convenção meteorológica). 0° = N, 90° = L.

import math
import time

try:
    from machine import ADC, I2C, Pin
except ImportError:          # permite testar a lógica no PC
    ADC = I2C = Pin = None

R_PULLUP = 10000.0           # resistor fixo do divisor (10 kΩ para 3V3)
VCC = 3.30                   # tensão do trilho 3V3, usada só sem o canal de referência (A3)

# Resistência de cada posição, na ordem de NOMES. Valores de referência do SparkFun Weather
# Meter Kit (mesmo fabricante). Na bancada (31/10/2026) a peça do projeto bateu com eles nas
# 8 direções principais. Depois de calibrar (teste_biruta_ads.py, MODO 2), cole a tabela aqui.
R_TAB = (33000, 6570, 8200, 891, 1000, 688, 2200, 1410,
         3900, 3140, 16000, 14120, 120000, 42120, 64900, 21880)
NOMES = ("N", "NNE", "NE", "ENE", "L", "ESE", "SE", "SSE",
         "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO")

# Correção de instalação: se a marca "N" da biruta não ficou apontada para o norte real,
# coloque aqui quantos graus somar (ex.: a marca N aponta 30° a leste do norte -> 30).
OFFSET_GRAUS = 0.0

# Diagnóstico
LIM_CURTO = 0.03             # fração de VCC abaixo da qual é curto com o GND
R_MAX = 250000.0             # a maior posição é ~120 kΩ; acima disso é circuito aberto


class Ads1115:
    """Leitura single-shot mínima do ADS1115, sem biblioteca externa."""
    PGA_4V096 = 0b001        # ±4,096 V de fundo de escala (125 µV por passo)

    def __init__(self, i2c, endereco=0x48):
        self.i2c = i2c
        self.end = endereco
        self.buf = bytearray(2)

    def volts(self, canal):
        # OS=1 (inicia) | MUX=100+canal (AINx contra GND) | PGA ±4,096 V | single-shot
        # | 128 amostras/s | comparador desligado
        cfg = (0x8000 | ((0b100 | canal) << 12) | (self.PGA_4V096 << 9)
               | 0x0100 | (0b100 << 5) | 0b11)
        self.i2c.writeto_mem(self.end, 0x01, bytes((cfg >> 8, cfg & 0xFF)))
        time.sleep_ms(9)                         # 1/128 s + folga
        self.i2c.readfrom_mem_into(self.end, 0x00, self.buf)
        bruto = (self.buf[0] << 8) | self.buf[1]
        if bruto & 0x8000:
            bruto -= 0x10000
        return bruto * 4.096 / 32768


class Biruta:
    def __init__(self, ads=None, canal=1, canal_vcc=None, gpio_adc=None, amostras=8):
        """ads + canal: biruta no ADS1115 (oficial). canal_vcc: canal do ADS ligado no 3V3
        (opcional, deixa a leitura ratiométrica). gpio_adc=28: ADC interno (bancada)."""
        if ads is None and gpio_adc is None:
            raise ValueError("passe ads=Ads1115(...) ou gpio_adc=28")
        self.ads = ads
        self.canal = canal
        self.canal_vcc = canal_vcc
        self.adc = ADC(gpio_adc) if gpio_adc is not None else None
        self.amostras = amostras

    def fracao(self):
        """Tensão no ponto do divisor como fração do 3V3 (0 a 1), média de N leituras."""
        s = 0.0
        for _ in range(self.amostras):
            if self.ads is not None:
                v = self.ads.volts(self.canal)
                ref = self.ads.volts(self.canal_vcc) if self.canal_vcc is not None else VCC
                s += v / ref
            else:
                s += self.adc.read_u16() / 65535      # ADC interno usa o próprio 3V3 como ref.
        return s / self.amostras

    def resistencia(self):
        """Resistência da biruta em ohms (None se aberto, 0 se em curto)."""
        f = self.fracao()
        if f <= LIM_CURTO:
            return 0.0
        if f >= 0.999:
            return None
        r = R_PULLUP * f / (1.0 - f)
        return None if r > R_MAX else r

    def ler(self):
        """Devolve (índice 0-15, graus, nome, resistência) ou levanta OSError com o diagnóstico."""
        r = self.resistencia()
        if r is None:
            raise OSError("circuito aberto: confira os fios verde e preto e o resistor de 10 k")
        if r == 0.0:
            raise OSError("curto com o GND: confira a ligação")
        i = posicao(r)
        graus = (i * 22.5 + OFFSET_GRAUS) % 360
        return i, graus, NOMES[i], r


def posicao(r, tabela=None):
    """Posição da tabela mais próxima, comparando em escala log (as resistências vão de
    688 Ω a 120 kΩ, então a distância relativa é o que importa)."""
    tabela = tabela or R_TAB
    lr = math.log(r)
    melhor, menor = 0, 1e9
    for i, rt in enumerate(tabela):
        d = abs(lr - math.log(rt))
        if d < menor:
            melhor, menor = i, d
    return melhor


class MediaVetorial:
    """Direção predominante de um período (dia, hora). A média simples de ângulos falha
    (350° e 10° dariam 180°); somando vetores unitários dá 0°, que é o certo.

    constancia = tamanho do vetor médio, de 0 a 1: perto de 1, o vento ficou numa direção só;
    perto de 0, variou para todo lado (a predominante não quer dizer muita coisa).
    Quando o anemômetro chegar, passe a velocidade como peso em adicionar()."""

    def __init__(self):
        self.zerar()

    def zerar(self):
        self.sx = self.sy = self.peso = 0.0
        self.n = 0

    def adicionar(self, graus, peso=1.0):
        a = math.radians(graus)
        self.sx += peso * math.sin(a)
        self.sy += peso * math.cos(a)
        self.peso += peso
        self.n += 1

    def resultado(self):
        """(graus, nome do setor, constancia) ou None se não há leituras."""
        if self.n == 0 or self.peso == 0:
            return None
        graus = round(math.degrees(math.atan2(self.sx, self.sy)), 1) % 360
        constancia = math.sqrt(self.sx ** 2 + self.sy ** 2) / self.peso
        setor = NOMES[int((graus + 11.25) // 22.5) % 16]
        return graus, setor, constancia


def criar_padrao(canal_vcc=None):
    """Biruta no ADS1115 A1, no I²C0 da BitDogLab (SDA GPIO0, SCL GPIO1).
    Passe canal_vcc=3 se o A3 estiver ligado no 3V3."""
    i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
    return Biruta(ads=Ads1115(i2c), canal=1, canal_vcc=canal_vcc)
