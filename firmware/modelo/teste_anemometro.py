# AgroEdge - teste de bancada do anemômetro Met One 014A (MicroPython, BitDogLab).
# Copie anemometro.py, config_local.py e este arquivo para a placa (MicroPico, Thonny ou
# `mpremote cp anemometro.py config_local.py teste_anemometro.py :`) e rode este.
#
# Ligação oficial (GPIO17 = cfg.PINO_ANEMOMETRO, no conector IDC ao lado do GP16):
#   3V3 ──[10 kΩ]──┐
#   fio do sensor ─┴──[1 kΩ]──┬── GPIO17
#                          [100 nF]
#   outro fio ──── GND ───────┘
# Teste rápido sem componentes: um fio do par no GPIO17 e o outro no GND (o pull-up interno
# está sempre ligado). Qual é o par: ver LEIA-ME_ANEMOMETRO.md (multímetro em continuidade).
#
# MODO 1 (contato): mostra o estado do pino ao vivo (1 = aberto, 0 = fechado) e conta cada
#   fechamento. Gire a concha bem devagar com a mão: tem que contar 1 a cada fechamento.
# MODO 2 (medição): a cada 1 s mostra pulsos, f (Hz), v (m/s e km/h), u2, média e rajada
#   desde o início, e avisa se houve bordas rejeitadas pelo debounce (repique/ruído).
# MODO 3 (debounce): mostra o menor intervalo entre bordas e entre pulsos aceitos, para
#   conferir se o ANEMO_DEBOUNCE_MS está bom. Use com ventilador ou soprando forte.
# Botão A (GPIO5) passa para o próximo modo (1 -> 2 -> 3 -> 1). Ctrl+C para parar.

import time
from machine import Pin
import anemometro
import config_local as cfg

MODO = 1
SEM_PULSO_S = 10          # avisa se ficar esse tempo sem nenhum pulso

sensor = anemometro.Anemometro(arquivo=None)
botao_a = Pin(5, Pin.IN, Pin.PULL_UP)
_botao_antes = 1

print("Anemômetro no GPIO%d | v = %.3f × f + %.3f | altura %.1f m | debounce %d ms"
      % (sensor.pino_n, cfg.ANEMO_M, cfg.ANEMO_B, cfg.ANEMO_ALTURA_M, cfg.ANEMO_DEBOUNCE_MS))


def apertou():
    """True uma vez a cada aperto do botão A."""
    global _botao_antes
    agora = botao_a.value()
    borda = _botao_antes == 1 and agora == 0
    _botao_antes = agora
    if borda:
        time.sleep_ms(30)                  # debounce do botão
    return borda


def esperar(ms):
    """Dorme ms em pedaços, olhando o botão. True se apertou (trocar de modo)."""
    fim = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(fim, time.ticks_ms()) > 0:
        if apertou():
            return True
        time.sleep_ms(10)
    return False


def modo_contato():
    print("\n=== MODO 1: contato ===  gire a concha BEM devagar com a mão")
    print("Esperado: estado 1 (aberto) e, a cada fechamento, 0 e contagem +1.")
    print("Anote quantos fechamentos dá UMA volta completa das conchas.\n")
    sensor.medir()
    estado = sensor.pino.value()
    print("estado inicial: %d (%s)" % (estado, "aberto" if estado else "FECHADO"))
    fechamentos = 0                        # contados por varredura do pino (lento)
    pulsos_irq = 0                         # contados pela interrupção (o que vale)
    t_mudou = time.ticks_ms()
    while True:
        v = sensor.pino.value()
        if v != estado:
            estado = v
            t_mudou = time.ticks_ms()
            if v == 0:
                fechamentos += 1
            pulsos_irq += sensor.medir()[0]
            print("  pino = %d %-8s | fechamentos: %3d | pulsos na interrupção: %3d | "
                  "rejeitados: %d" % (v, "(FECHOU)" if v == 0 else "(abriu)", fechamentos,
                                      pulsos_irq, sensor.rejeitados_total))
        elif time.ticks_diff(time.ticks_ms(), t_mudou) > SEM_PULSO_S * 1000:
            t_mudou = time.ticks_ms()
            if estado:
                print("  nenhum fechamento em %d s (pino em 1): gire as conchas; se não mudar,"
                      " confira se é o par certo de fios e se um está no GPIO%d e o outro no"
                      " GND" % (SEM_PULSO_S, sensor.pino_n))
            else:
                print("  pino em 0 há %d s: a reed parou fechada (gire um pouco) ou o fio do"
                      " GPIO%d está em curto com o GND" % (SEM_PULSO_S, sensor.pino_n))
        if apertou():
            return
        time.sleep_ms(2)


def modo_medicao():
    print("\n=== MODO 2: medição (janela de 1 s) ===")
    print("Parado = 0 m/s. Girando com a mão: poucos m/s. Ventilador: ~2 a 6 m/s.\n")
    cab = " pulsos   f (Hz)   v (m/s)  v (km/h)  u2 (m/s) | média u2  rajada"
    sensor.medir()
    soma = tempo = rajada = 0.0
    sem_pulso = 0.0
    linhas = 0
    while True:
        if esperar(1000):
            return
        n, f, v = sensor.medir()
        dt = sensor.ultimo_dt
        u2 = anemometro.para_2m(v)
        soma += u2 * dt
        tempo += dt
        rajada = max(rajada, v)
        if linhas % 20 == 0:
            print(cab)
        linhas += 1
        print(" %5d   %6.2f   %6.2f   %6.1f    %6.2f  |  %6.2f   %6.2f"
              % (n, f, v, anemometro.km_h(v), u2, soma / tempo, rajada))
        if sensor.ultimos_rejeitados:
            print("   atenção: %d borda(s) a menos de %d ms da anterior foram rejeitadas "
                  "(repique da reed ou ruído no cabo); total: %d"
                  % (sensor.ultimos_rejeitados, cfg.ANEMO_DEBOUNCE_MS, sensor.rejeitados_total))
        if f > 60:
            print("   atenção: %.0f Hz é mais que os ~56 Hz de 45 m/s: provável ruído. "
                  "Use o 10 kΩ + filtro 1 kΩ/100 nF e cabo afastado de fios de força." % f)
        sem_pulso = sem_pulso + dt if n == 0 else 0.0
        if sem_pulso >= SEM_PULSO_S:
            print("   nenhum pulso em %d s: confira os fios (GPIO%d e GND) / gire as conchas"
                  % (SEM_PULSO_S, sensor.pino_n))
            sem_pulso = 0.0


def modo_debounce():
    print("\n=== MODO 3: debounce ===  ventilador ou sopro forte; mostra a cada 2 s\n")
    sensor.medir()
    sensor.zerar_diagnostico()
    f_max = 0.0
    while True:
        if esperar(2000):
            return
        n, f, v = sensor.medir()
        f_max = max(f_max, f)
        borda, ok = sensor.diagnostico()
        print(" aceitos: %5d | rejeitados: %4d | menor entre bordas: %s | menor entre "
              "pulsos aceitos: %s | f máx: %.1f Hz (%.1f m/s)"
              % (sensor.total, sensor.rejeitados_total,
                 "-" if borda is None else "%.2f ms" % borda,
                 "-" if ok is None else "%.2f ms" % ok, f_max, anemometro.velocidade(f_max)))
        if ok is not None and f_max > 0:
            esperado_ms = 1000.0 / f_max
            if ok < 0.5 * esperado_ms:
                print("   pulsos aceitos bem mais próximos que 1/f (%.1f ms): ainda passa "
                      "ruído; considere subir o ANEMO_DEBOUNCE_MS (máx. ~10 ms)" % esperado_ms)
        if borda is not None and borda < cfg.ANEMO_DEBOUNCE_MS and sensor.rejeitados_total:
            print("   há repique abaixo de %d ms e o debounce está filtrando (normal em reed)"
                  % cfg.ANEMO_DEBOUNCE_MS)


MODOS = {1: modo_contato, 2: modo_medicao, 3: modo_debounce}
modo = MODO
while True:
    MODOS[modo]()
    modo = modo % 3 + 1
    print("\n[botão A] indo para o MODO %d" % modo)
