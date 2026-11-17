# AgroEdge - válvula solenoide pelo relé.
#
# Liga o relé por um tempo (comando manual da plataforma ou irrigação automática) e devolve o
# que foi aplicado, em minutos e em mm (pela vazão e área por planta do config).
#
# config_local.py:
#   PINO_RELE = 19            GPIO do IN do módulo de relé
#   RELE_NIVEL_BAIXO = True   módulo "low level trigger" (liga com o IN em 0 V), o mais comum
#   RELE_DRENO_ABERTO = False True se o módulo de 5 V, sem o jumper JD-VCC, não desligar com o
#                             IN em 3,3 V: o pino "solta" e o próprio módulo puxa para cima
# O pino já nasce no nível de DESLIGADO, para o relé não estalar quando a placa liga.

import time

import config_local as cfg


def _c(nome, padrao):
    return getattr(cfg, nome, padrao)


class Valvula:
    def __init__(self):
        self.pino = None
        self.aberta = None        # dict: id, ts_inicio, fim_ms, origem, cmd_id
        self.baixo = _c("RELE_NIVEL_BAIXO", True)
        try:
            from machine import Pin
            modo = Pin.OUT
            if self.baixo and _c("RELE_DRENO_ABERTO", False):
                modo = getattr(Pin, "OPEN_DRAIN", Pin.OUT)
            self.pino = Pin(_c("PINO_RELE", 19), modo, value=self._nivel(False))
        except Exception as e:
            print("relé indisponível:", e)

    def _nivel(self, ligado):
        return (0 if ligado else 1) if self.baixo else (1 if ligado else 0)

    def abrir(self, minutos, origem, cmd_id, ts):
        """Liga o relé por `minutos`. Devolve o payload "iniciada" para a plataforma."""
        self.aberta = {"id": "%d-%s" % (ts, "auto" if origem == "automatica" else "manual"),
                       "ts_inicio": ts, "origem": origem, "cmd_id": cmd_id,
                       "fim_ms": time.ticks_add(time.ticks_ms(), int(minutos * 60000))}
        if self.pino:
            self.pino.value(self._nivel(True))
        print("válvula ABERTA (%s), %.1f min" % (origem, minutos))
        return self.payload(None, None, None, "iniciada")

    def venceu(self):
        return self.aberta is not None and \
            time.ticks_diff(time.ticks_ms(), self.aberta["fim_ms"]) >= 0

    def fechar(self, estado, ts):
        """Desliga o relé. Devolve (payload final, mm aplicados)."""
        if self.pino:
            self.pino.value(self._nivel(False))
        v = self.aberta
        minutos = round((ts - v["ts_inicio"]) / 60, 1)
        mm = round(minutos / 60 * cfg.VAZAO_L_H / cfg.AREA_M2, 2)
        p = self.payload(ts, minutos, mm, estado)
        self.aberta = None
        print("válvula fechada (%s): %.1f min, %.2f mm" % (estado, minutos, mm))
        return p, mm

    def payload(self, ts_fim, minutos, mm, estado):
        v = self.aberta
        return {"id": v["id"], "ts_inicio": v["ts_inicio"], "ts_fim": ts_fim, "minutos": minutos,
                "mm": mm, "origem": v["origem"], "cmd_id": v["cmd_id"], "estado": estado}
