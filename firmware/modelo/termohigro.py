# AgroEdge - temperatura e umidade do ar com o AM2302.
# MicroPython (BitDogLab / RP2040). O AM2302 é o DHT22 em versão com fios (mesmo fabricante,
# Aosong, e mesmo protocolo de 1 fio), então usa o driver dht.DHT22 que já vem no MicroPython.
#
# Ligação (pino em config_local.PINO_AM2302, padrão GPIO17, conector IDC fileira
# "GND GP16 GP17 GND GP28 3V3 GND"):
#   VCC  -> 3V3          DATA -> GPIO17 (com pull-up de 10 kΩ para 3V3)
#   GND  -> GND
# Cabo curto (até ~3 m). No campo, o AM2302 vai dentro de um abrigo contra radiação
# (pratinhos empilhados, ventilado e na sombra), longe do solo e da caixa. Ao sol direto a
# temperatura sai vários graus acima da real e o ET0 fica errado.
#
# O AM2302 só pode ser lido a cada 2 s e às vezes falha (erro de checksum ou timeout): por
# isso ler() tenta de novo e devolve None se todas as tentativas falharem.
#
# Uso:
#   import termohigro
#   th = termohigro.Termohigro()
#   t, ur = th.ler()           # °C e %, ou (None, None)
#   th.adicionar(t, ur)        # soma no dia (máx/mín de T e UR, média de UR)
#   th.salvar()                # de vez em quando
#   r = th.fechar_dia()        # dict com tmax, tmin, ur_media, ur_max, ur_min, n; e zera

import json
import time

try:
    import dht
    from machine import Pin
except ImportError:          # permite testar a lógica no PC
    dht = Pin = None

try:
    import config_local as cfg
except ImportError:
    cfg = None

INTERVALO_MIN_MS = 2100      # o AM2302 precisa de ~2 s entre leituras

# leituras fora disso são lixo de comunicação, não clima
T_MIN, T_MAX = -10.0, 60.0
UR_MIN, UR_MAX = 0.0, 100.0


def valida(t, ur):
    return (t is not None and ur is not None and T_MIN <= t <= T_MAX
            and UR_MIN <= ur <= UR_MAX)


class Termohigro:
    def __init__(self, pino=None, arquivo: "str | None" = "ar_hoje.json"):
        self.arquivo = arquivo
        self.falhas = 0
        self._ultima_ms = None
        self.sensor = None
        if dht is not None:
            n = getattr(cfg, "PINO_AM2302", 17) if pino is None else pino
            self.sensor = dht.DHT22(Pin(n, Pin.IN, Pin.PULL_UP))     # AM2302 = DHT22
        self._zerar()
        if arquivo:
            try:
                with open(arquivo) as f:
                    e = json.load(f)
                for k in ("tmax", "tmin", "urmax", "urmin", "soma_ur", "n"):
                    setattr(self, k, e[k])
            except (OSError, ValueError, KeyError):
                pass
        self._n_salvo = self.n

    def _zerar(self):
        self.tmax = self.tmin = self.urmax = self.urmin = None
        self.soma_ur = 0.0
        self.n = 0

    def ler(self, tentativas=3):
        """(temperatura °C, UR %) ou (None, None) se o sensor não respondeu."""
        if self.sensor is None:
            raise OSError("Termohigro.ler precisa da placa")
        for _ in range(tentativas):
            if self._ultima_ms is not None:
                falta = INTERVALO_MIN_MS - time.ticks_diff(time.ticks_ms(), self._ultima_ms)
                if falta > 0:
                    time.sleep_ms(falta)
            self._ultima_ms = time.ticks_ms()
            try:
                self.sensor.measure()
                t, ur = self.sensor.temperature(), self.sensor.humidity()
                if valida(t, ur):
                    return t, ur
            except OSError:
                pass
            self.falhas += 1
        return None, None

    def adicionar(self, t, ur):
        if not valida(t, ur):
            return
        self.tmax = t if self.tmax is None or t > self.tmax else self.tmax
        self.tmin = t if self.tmin is None or t < self.tmin else self.tmin
        self.urmax = ur if self.urmax is None or ur > self.urmax else self.urmax
        self.urmin = ur if self.urmin is None or ur < self.urmin else self.urmin
        self.soma_ur += ur
        self.n += 1

    def salvar(self):
        if self.arquivo and self.n != self._n_salvo:
            with open(self.arquivo, "w") as f:
                json.dump({"tmax": self.tmax, "tmin": self.tmin, "urmax": self.urmax,
                           "urmin": self.urmin, "soma_ur": self.soma_ur, "n": self.n}, f)
            self._n_salvo = self.n

    def fechar_dia(self):
        r = {"tmax": self.tmax, "tmin": self.tmin, "ur_max": self.urmax, "ur_min": self.urmin,
             "ur_media": self.soma_ur / self.n if self.n else None, "n": self.n}
        self._zerar()
        self._n_salvo = -1
        self.salvar()
        return r


if __name__ == "__main__":
    if dht is None:
        th = Termohigro(arquivo=None)
        for t, u in ((25.0, 60.0), (31.5, 40.0), (21.0, 85.0), (99.0, 50.0), (None, 10.0)):
            th.adicionar(t, u)
        r = th.fechar_dia()
        assert r["tmax"] == 31.5 and r["tmin"] == 21.0 and r["n"] == 3, r
        assert abs(r["ur_media"] - 61.6667) < 1e-3 and r["ur_max"] == 85.0 and r["ur_min"] == 40.0
        print("OK", r)
    else:
        # teste na placa: lê a cada 2 s e mostra
        th = Termohigro(arquivo=None)
        print("AM2302 no GPIO", getattr(cfg, "PINO_AM2302", 17))
        while True:
            t, u = th.ler()
            if t is None:
                print("sem resposta (falhas: %d): confira VCC 3V3, GND, DATA e o pull-up" % th.falhas)
            else:
                print("T = %.1f °C   UR = %.1f %%" % (t, u))
            time.sleep(2)
