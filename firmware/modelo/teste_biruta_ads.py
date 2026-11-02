# AgroEdge - teste oficial da biruta pelo ADS1115 (MicroPython, BitDogLab).
# Copie biruta.py e este arquivo para a placa (MicroPico, Thonny ou
# `mpremote cp biruta.py teste_biruta_ads.py :`) e rode este.
#
# Ligação: ADS1115 no I²C0 (SDA GPIO0, SCL GPIO1, VDD 3V3, GND, ADDR no GND -> 0x48).
#   3V3 ──[10 kΩ]──┬── ADS1115 A1
#                  │
#            fio VERDE da biruta
#            fio PRETO da biruta ── GND
#   Opcional (recomendado): A3 direto no 3V3 e CANAL_VCC = 3 (leitura ratiométrica).
#
# MODO 1 (leitura): gire a seta e confira se a direção muda a cada 22,5°. Mostra também a
#   direção predominante desde o início (média vetorial).
# MODO 2 (calibração): aponte a seta para cada uma das 16 posições, na ordem N, NNE, NE...,
#   aperte o botão A em cada uma; no fim ele imprime a R_TAB medida para colar no biruta.py.

import time
from machine import I2C, Pin
import biruta

MODO = 1
CANAL_VCC = None      # 3 se o A3 do ADS1115 estiver ligado no 3V3 (leitura ratiométrica)

i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
achados = i2c.scan()
print("I2C0 encontrou:", [hex(a) for a in achados])
if 0x48 not in achados:
    raise SystemExit("ADS1115 não respondeu em 0x48: confira SDA (GPIO0), SCL (GPIO1), 3V3, GND"
                     " e o pino ADDR no GND")
ads = biruta.Ads1115(i2c)
sensor = biruta.Biruta(ads=ads, canal=1, canal_vcc=CANAL_VCC)
if CANAL_VCC is not None:
    print("Trilho 3V3 medido no A%d: %.3f V" % (CANAL_VCC, ads.volts(CANAL_VCC)))


def leitura():
    media = biruta.MediaVetorial()
    print("Gire a seta. Ctrl+C para parar.\n")
    print("  fração   resistência   direção    | predominante até agora")
    while True:
        try:
            i, graus, nome, r = sensor.ler()
            media.adicionar(graus)
            g, setor, const = media.resultado()
            print("  %.3f    %8.0f Ω    %-3s %5.1f° | %s (%.0f°, constância %.2f)"
                  % (sensor.fracao(), r, nome, graus, setor, g, const))
        except OSError as e:
            print("  ERRO:", e)
        time.sleep_ms(500)


def calibracao():
    botao_a = Pin(5, Pin.IN, Pin.PULL_UP)
    medidas = []
    print("Comece com a seta na marca N da biruta e vá no sentido horário.")
    print("As intermediárias (NNE, ENE...) são estreitas: gire devagar até a leitura ao vivo")
    print("mudar e só então aperte A.\n")
    for nome in biruta.NOMES:
        print("Aponte a seta para %-3s e aperte o botão A..." % nome)
        ultimo = None
        while botao_a.value():
            r_vivo = sensor.resistencia()
            if r_vivo != ultimo and (r_vivo is None or not ultimo
                                     or abs(r_vivo - ultimo) / ultimo > 0.03):
                print("      agora: %s" % ("ABERTO" if r_vivo is None else "%.0f Ω" % r_vivo))
                ultimo = r_vivo
            time.sleep_ms(80)
        r = sensor.resistencia()
        medidas.append(r)
        print("   %s: %s" % (nome, "ABERTO" if r is None else "%.0f Ω" % r))
        while not botao_a.value():          # espera soltar
            time.sleep_ms(20)
        time.sleep_ms(250)
    print("\nCole no biruta.py:")
    print("R_TAB = (" + ", ".join("%.0f" % (m or 0) for m in medidas) + ")")
    validas = sorted(m for m in medidas if m)
    for a, b in zip(validas, validas[1:]):
        if b / a < 1.08:
            print("Atenção: %.0f e %.0f Ω estão a menos de 8%% um do outro" % (a, b))
    if len(validas) < 16:
        print("Atenção: alguma posição deu ABERTO. Confira o contato e repita.")


leitura() if MODO == 1 else calibracao()
