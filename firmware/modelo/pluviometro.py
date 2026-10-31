# AgroEdge - leitura do pluviômetro de báscula (tipo Misol/Fine Offset, cabo RJ11).
# Dentro dele há uma "gangorra" com duas canecas: cada vez que uma enche, ela vira e um ímã
# passa por um reed switch, que fecha o contato por um instante. Não há protocolo digital:
# cada virada é UM pulso, e cada pulso vale MM_POR_PULSO de chuva (config_local.py).
#
# Ligação: os dois fios do meio do RJ11 (o par que fecha quando a báscula vira; confira com
# o multímetro) vão um no pino cfg.PINO_PLUVIOMETRO e o outro no GND. O pull-up interno do
# RP2040 deixa o pino em 1; a virada leva o pino a 0 por um instante.
#
# Uso:
#   p = pluviometro.Pluviometro()     # começa a contar (carrega a contagem salva do dia, se houver)
#   p.chuva_mm()                      # chuva acumulada desde o último fechar_dia
#   p.salvar()                        # de vez em quando, no laço principal (não perde a chuva se reiniciar)
#   chuva = p.fechar_dia()            # no fim do dia: devolve os mm e zera; vai para historico.fechar_dia
#
# Calibração (mede o MM_POR_PULSO deste aparelho):
#   1. meça a boca do funil por dentro, em cm, e calcule a área A (comprimento × largura)
#   2. rode este arquivo e despeje bem devagar um volume V conhecido (ex.: 100 mL, com seringa)
#   3. MM_POR_PULSO = (V / A × 10) / pulsos      (1 mL sobre 1 cm² dá 10 mm)
#   Repita 3 vezes e use a média. Com o aparelho nivelado pela bolha do funil.

import json
import time
import machine
from machine import Pin
import config_local as cfg

# o reed switch "quica" alguns ms ao fechar; pulsos mais próximos que isso são o mesmo
# (chuva forte de 100 mm/h dá uma virada a cada ~10 s, então 200 ms está longe de perder pulso)
DEBOUNCE_MS = 200


class Pluviometro:
    # arquivo=None: só conta, não grava na flash (usado no teste). A anotação entre aspas é só
    # para o Pylance; o MicroPython ignora anotações.
    def __init__(self, pino=cfg.PINO_PLUVIOMETRO, arquivo: "str | None" = "chuva_hoje.json"):
        self.arquivo = arquivo
        self.pulsos = 0
        self.salvos = 0
        self.ultimo_ms = time.ticks_ms()
        if arquivo:
            try:
                with open(arquivo) as f:
                    self.pulsos = self.salvos = json.load(f)["pulsos"]
            except (OSError, ValueError, KeyError):
                pass                     # primeiro uso ou arquivo estragado: começa do zero
        self.pino = Pin(pino, Pin.IN, Pin.PULL_UP)
        self.pino.irq(trigger=Pin.IRQ_FALLING, handler=self._virou)

    def _virou(self, pino):
        """Interrupção: roda sozinha a cada virada da báscula. Só conta, nada de arquivo aqui."""
        agora = time.ticks_ms()
        if time.ticks_diff(agora, self.ultimo_ms) > DEBOUNCE_MS:
            self.pulsos += 1
        self.ultimo_ms = agora

    def chuva_mm(self):
        return self.pulsos * cfg.MM_POR_PULSO

    def salvar(self):
        """Grava a contagem na flash, só se mudou (a flash gasta com escritas demais)."""
        if self.arquivo and self.pulsos != self.salvos:
            n = self.pulsos
            with open(self.arquivo, "w") as f:
                json.dump({"pulsos": n}, f)
            self.salvos = n

    def fechar_dia(self):
        """Devolve a chuva do dia em mm e recomeça a contagem."""
        estado = machine.disable_irq()   # pausa a interrupção para não perder uma virada no meio
        n = self.pulsos
        self.pulsos = 0
        machine.enable_irq(estado)
        if self.arquivo:
            self.salvar()
        return n * cfg.MM_POR_PULSO


if __name__ == "__main__":
    # teste: rode este arquivo na placa e despeje água devagar no funil
    p = Pluviometro(arquivo=None)
    print("contando no pino", cfg.PINO_PLUVIOMETRO, "- vire a báscula com o dedo ou despeje água")
    visto = 0
    while True:
        if p.pulsos != visto:
            visto = p.pulsos
            print("pulsos:", visto, " chuva: %.2f mm" % p.chuva_mm())
        time.sleep_ms(50)
