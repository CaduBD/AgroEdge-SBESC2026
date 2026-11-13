"""Simulador de placas BitDogLab do AgroEdge.

Implementa o lado da placa do contrato MQTT (seção 7 da especificação): telemetria,
fechamento diário, irrigação, resposta a comandos, status com LWT e configuração retida.
Serve para desenvolver o painel sem a placa.

Exemplos (a partir de plataforma/):

    python simulador/simulador.py                         # placa padrão do .env, tempo real
    python simulador/simulador.py --inicio 2026-11-01 --acelerar 96
    python simulador/simulador.py --dias 3 --acelerar 288     # 3 dias de histórico em 15 min
    python simulador/simulador.py --queda 02:00-04:00     # rede fora todo dia das 2h às 4h

Relógio: com --inicio, o tempo simulado começa nessa data e corre --acelerar vezes mais
rápido até alcançar a hora real; daí em diante segue em tempo real (o servidor rejeita
ts mais de 24 h no futuro, então o simulador nunca passa da hora real).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import math
import random
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

RAIZ = Path(__file__).resolve().parents[1]  # plataforma/
CATALOGO = RAIZ / "backend" / "app" / "catalogo" / "culturas.json"
FIRMWARE = RAIZ.parent / "firmware" / "modelo"

FUSO = timezone(timedelta(hours=-3), "America/Bahia")  # UTC−3, sem horário de verão
LATITUDE = -9.39  # Petrolina
ALTITUDE_M = 370.0  # igual ao config_local.py do firmware
LOTE_MAXIMO = 50
HISTORICO_CONFIAVEL_DIAS = 28

CONFIG_PADRAO: dict[str, Any] = {
    "cfg_v": None,
    "instalacao_id": None,
    "cultura": "manga_tommy_atkins",
    "data_referencia": None,  # None = 42 dias antes do início da simulação
    "agua_disp": 0.11,
    "raiz_m": None,
    "eficiencia": 0.9,
    "area_m2": 40.0,
    "vazao_l_h": 64.0,
    "n_plantas": None,
    "fonte_irrigacao": "tempo",
    "inicio_uso": "meio",
    "irrigacao_automatica": True,
    "hora_irrigacao": "05:00",
    "intervalo_telemetria_min": 15,
}

log = logging.getLogger("simulador")


# ---------------------------------------------------------------- utilidades


def br(valor: float | None, casas: int = 1) -> str:
    """Número no formato brasileiro (vírgula decimal)."""
    return "—" if valor is None else f"{valor:.{casas}f}".replace(".", ",")


def local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, FUSO)


def ts_local(dia: date, hora: int = 0, minuto: int = 0) -> int:
    return int(datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=FUSO).timestamp())


def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    arquivo = RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                env[chave.strip()] = valor.strip()
    return env


def carregar_catalogo() -> dict[str, dict[str, Any]]:
    try:
        return {c["chave"]: c for c in json.loads(CATALOGO.read_text(encoding="utf-8"))}
    except OSError:
        log.warning("catálogo não encontrado em %s; usando só a manga", CATALOGO)
        return {
            "manga_tommy_atkins": {
                "chave": "manga_tommy_atkins",
                "ciclo_dias": 149,
                "p": 0.5,
                "raiz_m": 0.6,
                "fases": [{"chave": "floracao", "dias": 149, "kc": 0.7}],
            }
        }


FW_ETO: Any = None  # módulo firmware/modelo/eto.py, se disponível
FW_CULTURAS: Any = None  # módulo firmware/modelo/culturas.py, se disponível


def _importar(nome: str) -> Any:
    """Importa um arquivo do firmware pelo caminho, sem pôr a pasta no sys.path
    (lá também há config_local.py e main.py, que não devem ser importados aqui)."""
    caminho = FIRMWARE / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(f"firmware_{nome}", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def carregar_firmware() -> bool:
    """Usa eto.py e culturas.py do firmware (os mesmos números da placa). Sem o firmware,
    cai no Penman-Monteith próprio e no Kc do catálogo da plataforma."""
    global FW_ETO, FW_CULTURAS
    try:
        FW_ETO, FW_CULTURAS = _importar("eto"), _importar("culturas")
    except Exception as erro:  # noqa: BLE001 -- firmware ausente ou com erro: segue sozinho
        log.info("firmware indisponível em %s (%s): usando ET₀ e Kc próprios", FIRMWARE, erro)
        FW_ETO = FW_CULTURAS = None
        return False
    log.info("usando eto.py e culturas.py do firmware em %s", FIRMWARE)
    return True


# ---------------------------------------------------------------- relógio


class Relogio:
    def __init__(self, inicio: datetime | None, acelerar: float) -> None:
        self.real0 = time.time()
        self.sim0 = inicio.timestamp() if inicio else self.real0
        self.fator = acelerar if inicio else 1.0

    def agora(self) -> float:
        real = time.time()
        return min(self.sim0 + (real - self.real0) * self.fator, real)

    def alcancou(self) -> bool:
        return self.agora() >= time.time() - 1


# ---------------------------------------------------------------- clima de Petrolina


def clima(serial: str, ts: int) -> dict[str, float]:
    """Clima plausível para o fim de um intervalo: curva diária + ruído reprodutível."""
    momento = local(ts)
    hora = momento.hour + momento.minute / 60
    dia = random.Random(f"{serial}-{momento.date()}")
    ruido = random.Random(f"{serial}-{ts}")

    offset_dia = dia.uniform(-1.5, 1.5)
    nublado = dia.random() < 0.15
    chuvoso = dia.random() < 0.06

    temp = 28.5 + offset_dia + 6.5 * math.sin(2 * math.pi * (hora - 9) / 24) + ruido.gauss(0, 0.3)
    ur = max(15.0, min(98.0, 78 - (temp - 22) * 3.4 + ruido.gauss(0, 1.5) + (15 if chuvoso else 0)))
    sol = max(0.0, math.sin(math.pi * (hora - 6) / 12)) if 6 <= hora <= 18 else 0.0
    rad = 920 * sol * (0.55 if nublado or chuvoso else 1.0) * ruido.uniform(0.92, 1.0)
    vento = max(0.3, 2.5 + 1.2 * math.sin(2 * math.pi * (hora - 14) / 24) + ruido.gauss(0, 0.3))
    chuva = ruido.uniform(0.2, 3.0) if chuvoso and 14 <= hora <= 17 else 0.0
    return {
        "temp_c": round(temp, 1),
        "ur_pct": round(ur, 1),
        "vento_ms": round(min(vento, 4.5), 1),
        "rad_wm2": round(rad, 0),
        "chuva_mm": round(chuva, 1),
    }


def et0_penman_monteith(
    tmax: float, tmin: float, ur: float, u2: float, rs: float, dia: date
) -> float:
    """ET₀ diária FAO-56 (mm/dia). rs em MJ/m²/dia."""

    def e0(t: float) -> float:
        return 0.6108 * math.exp(17.27 * t / (t + 237.3))

    t = (tmax + tmin) / 2
    delta = 4098 * e0(t) / (t + 237.3) ** 2
    pressao = 101.3 * ((293 - 0.0065 * ALTITUDE_M) / 293) ** 5.26
    gama = 0.000665 * pressao
    es = (e0(tmax) + e0(tmin)) / 2
    ea = es * ur / 100

    j = dia.timetuple().tm_yday
    phi = math.radians(LATITUDE)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    dec = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(dec))
    ra = (
        (24 * 60 / math.pi)
        * 0.082
        * dr
        * (ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))
    )
    rso = (0.75 + 2e-5 * ALTITUDE_M) * ra
    rns = 0.77 * rs
    rnl = (
        4.903e-9
        * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4)
        / 2
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * min(rs / rso, 1.0) - 0.35)
    )
    rn = rns - rnl
    et0 = (0.408 * delta * rn + gama * 900 / (t + 273) * u2 * (es - ea)) / (
        delta + gama * (1 + 0.34 * u2)
    )
    return max(0.0, et0)


# ---------------------------------------------------------------- placa


@dataclass
class Valvula:
    id: str
    ts_inicio: int
    ts_fim_previsto: int
    origem: str
    cmd_id: str | None


@dataclass
class Placa:
    serial: str
    usuario: str
    senha: str
    inicio_sim: float
    queda: tuple[int, int] | None  # minutos do dia (local), [inicio, fim)
    catalogo: dict[str, dict[str, Any]]
    cfg: dict[str, Any] = field(default_factory=lambda: dict(CONFIG_PADRAO))
    seq: int = 0
    seq_diario: int = 0
    proximo_ts: int = 0
    dia_atual: date | None = None
    leituras_dia: list[dict[str, Any]] = field(default_factory=list)
    irrigado_dia_mm: float = 0.0
    deficit: float = 0.0
    dias_historico: int = 0
    ultima_lamina: float = 0.0
    ultimo_dia_irrigado: date | None = None
    valvula: Valvula | None = None
    cmds_executados: set[str] = field(default_factory=set)
    buffer: list[tuple[str, Any]] = field(default_factory=list)  # (tipo, payload)
    lock: threading.RLock = field(default_factory=threading.RLock)
    cliente: mqtt.Client | None = None
    conectado: threading.Event = field(default_factory=threading.Event)
    relogio: Callable[[], float] = time.time

    def __post_init__(self) -> None:
        intervalo = self.intervalo_s
        self.proximo_ts = int(math.ceil(self.inicio_sim / intervalo) * intervalo)
        if self.cfg["data_referencia"] is None:
            ref = local(self.inicio_sim).date() - timedelta(days=42)
            self.cfg["data_referencia"] = ref.isoformat()

    # ------------------------------------------------------------ MQTT

    def topico(self, tipo: str) -> str:
        return f"agroedge/{self.serial}/{tipo}"

    def conectar(self, host: str, porta: int) -> None:
        cliente = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.serial,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        cliente.username_pw_set(self.usuario, self.senha)
        cliente.will_set(self.topico("status"), "offline", qos=1, retain=True)
        cliente.on_connect = self._ao_conectar
        cliente.on_disconnect = self._ao_desconectar
        cliente.on_message = self._ao_receber
        cliente.reconnect_delay_set(1, 30)
        self.cliente = cliente
        cliente.connect_async(host, porta, keepalive=60)
        cliente.loop_start()

    def _ao_conectar(self, cliente, _userdata, _flags, codigo, _props) -> None:  # type: ignore[no-untyped-def]
        if codigo.is_failure:
            self.log(f"conexão recusada pelo broker: {codigo}")
            return
        cliente.subscribe([(self.topico("config"), 1), (self.topico("cmd"), 1)])
        cliente.publish(self.topico("status"), "online", qos=1, retain=True)
        self.conectado.set()
        self.log("conectado; status online")

    def _ao_desconectar(self, _cliente, _userdata, _flags, codigo, _props) -> None:  # type: ignore[no-untyped-def]
        self.conectado.clear()
        self.log(f"desconectado ({codigo})")

    def _ao_receber(self, _cliente, _userdata, msg) -> None:  # type: ignore[no-untyped-def]
        try:
            dados = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.log(f"payload inválido em {msg.topic}")
            return
        with self.lock:
            if msg.topic.endswith("/config"):
                self.aplicar_config(dados)
            elif msg.topic.endswith("/cmd"):
                self.executar_comando(dados)

    def publicar(self, tipo: str, payload: Any, forcar: bool = False) -> None:
        """Publica ou, se a rede estiver "fora" (--queda), guarda no buffer."""
        if not forcar and self.em_queda(self.relogio()):
            self.buffer.append((tipo, payload))
            return
        assert self.cliente is not None
        self.cliente.publish(self.topico(tipo), json.dumps(payload, ensure_ascii=False), qos=1)

    def log(self, texto: str) -> None:
        log.info("[%s] %s", self.serial, texto)

    # ------------------------------------------------------------ config e comandos

    @property
    def intervalo_s(self) -> int:
        return int(self.cfg.get("intervalo_telemetria_min") or 15) * 60

    def aplicar_config(self, nova: dict[str, Any]) -> None:
        if nova.get("instalacao_id") != self.cfg.get("instalacao_id"):
            # Outro local: zera o histórico do classificador.
            self.deficit = 0.0
            self.dias_historico = 0
            self.log(f"nova instalação {nova.get('instalacao_id')}: histórico zerado")
        self.cfg.update({k: v for k, v in nova.items() if k in CONFIG_PADRAO})
        self.log(
            f"config v{self.cfg['cfg_v']} aplicada: {self.cfg['cultura']} "
            f"ref={self.cfg['data_referencia']} instalação={self.cfg['instalacao_id']}"
        )

    def executar_comando(self, cmd: dict[str, Any]) -> None:
        cmd_id = str(cmd.get("id", ""))
        if not cmd_id or cmd_id in self.cmds_executados:
            return
        self.cmds_executados.add(cmd_id)
        agora = int(self.relogio())
        acao, minutos = cmd.get("acao"), cmd.get("minutos")

        if time.time() > float(cmd.get("valido_ate") or 0):
            resultado = "recusado_vencido"
        elif acao == "abrir":
            if not isinstance(minutos, int | float) or not 1 <= minutos <= 120:
                resultado = "recusado_invalido"
            elif self.valvula is not None:
                resultado = "recusado_em_andamento"
            else:
                self.abrir_valvula(agora, float(minutos), "manual", cmd_id)
                resultado = "executado"
        elif acao == "cancelar":
            if self.valvula is not None:
                self.fechar_valvula(agora, "cancelada")
            resultado = "executado"
        else:
            resultado = "recusado_invalido"

        self.publicar("cmd_resp", {"id": cmd_id, "ts": agora, "resultado": resultado}, forcar=True)
        self.log(f"comando {acao} {minutos or ''} → {resultado}")

    # ------------------------------------------------------------ válvula

    def abrir_valvula(self, ts: int, minutos: float, origem: str, cmd_id: str | None) -> None:
        sufixo = "auto" if origem == "automatica" else "manual"
        self.valvula = Valvula(f"{ts}-{sufixo}", ts, ts + int(minutos * 60), origem, cmd_id)
        self.publicar("irrigacao", self._payload_irrigacao(None, "iniciada"))
        self.log(f"válvula aberta ({origem}) por {br(minutos)} min")

    def fechar_valvula(self, ts: int, estado: str) -> None:
        if self.valvula is None:
            return
        payload = self._payload_irrigacao(ts, estado)
        self.irrigado_dia_mm += payload["mm"]
        self.publicar("irrigacao", payload)
        self.log(
            f"válvula fechada ({estado}): {br(payload['minutos'])} min, {br(payload['mm'])} mm"
        )
        self.valvula = None

    def _payload_irrigacao(self, ts_fim: int | None, estado: str) -> dict[str, Any]:
        v = self.valvula
        assert v is not None
        minutos = mm = None
        if ts_fim is not None:
            minutos = round((ts_fim - v.ts_inicio) / 60, 1)
            mm = round(minutos / 60 * self.cfg["vazao_l_h"] / self.cfg["area_m2"], 2)
        return {
            "id": v.id,
            "ts_inicio": v.ts_inicio,
            "ts_fim": ts_fim,
            "minutos": minutos,
            "mm": mm,
            "origem": v.origem,
            "cmd_id": v.cmd_id,
            "estado": estado,
        }

    # ------------------------------------------------------------ rede (--queda)

    def em_queda(self, ts: float) -> bool:
        if self.queda is None:
            return False
        m = local(ts)
        minuto = m.hour * 60 + m.minute
        ini, fim = self.queda
        return ini <= minuto < fim if ini <= fim else (minuto >= ini or minuto < fim)

    def esvaziar_buffer(self, leitura_atual: dict[str, Any]) -> None:
        """Volta da rede: primeiro a leitura mais recente, depois o atrasado (antigo → novo)."""
        atrasadas = [p for t, p in self.buffer if t == "telemetria"]
        outras = [(t, p) for t, p in self.buffer if t != "telemetria"]
        self.buffer.clear()
        leitura_atual["buf"] = len(atrasadas)
        self.publicar("telemetria", leitura_atual, forcar=True)
        self.log(f"rede de volta: enviando {len(atrasadas)} leituras atrasadas")
        restantes = len(atrasadas)
        for i in range(0, len(atrasadas), LOTE_MAXIMO):
            lote = atrasadas[i : i + LOTE_MAXIMO]
            restantes -= len(lote)
            for item in lote:
                item["buf"] = restantes
            self.publicar("telemetria", lote, forcar=True)
        for tipo, payload in outras:
            self.publicar(tipo, payload, forcar=True)

    # ------------------------------------------------------------ ciclo da placa

    def avancar(self, agora: float) -> None:
        """Processa tudo o que aconteceu até `agora` (tempo simulado)."""
        with self.lock:
            while self.proximo_ts <= agora:
                ts = self.proximo_ts
                if self.valvula and self.valvula.ts_fim_previsto <= ts:
                    self.fechar_valvula(self.valvula.ts_fim_previsto, "concluida")
                self._virar_dia(ts)
                self._irrigacao_automatica(ts)
                self._telemetria(ts)
                self.proximo_ts = ts + self.intervalo_s
            if self.valvula and self.valvula.ts_fim_previsto <= agora:
                self.fechar_valvula(self.valvula.ts_fim_previsto, "concluida")

    def _telemetria(self, ts: int) -> None:
        self.seq += 1
        valores = clima(self.serial, ts)
        leitura = {
            "ts": ts,
            "seq": self.seq,
            "instalacao_id": self.cfg["instalacao_id"],
            "cfg_v": self.cfg["cfg_v"],
            **valores,
            "rssi": random.Random(ts).randint(-75, -58),
            "bat_v": None,
            "buf": 0,
        }
        self.leituras_dia.append(leitura)
        em_queda = self.em_queda(ts)
        quando = local(ts).strftime("%d/%m %H:%M")
        if not em_queda and self.buffer:
            self.esvaziar_buffer(leitura)
        else:
            if em_queda:
                leitura["buf"] = sum(1 for t, _ in self.buffer if t == "telemetria") + 1
            self.publicar("telemetria", leitura)
        estado = f"buf={leitura['buf']}" + (" (rede fora)" if em_queda else "")
        self.log(f"telemetria {quando} temp={br(valores['temp_c'])} {estado}")

    def _irrigacao_automatica(self, ts: int) -> None:
        if not self.cfg["irrigacao_automatica"] or self.valvula or self.ultima_lamina <= 0:
            return
        m = local(ts)
        hh, mm = (int(x) for x in str(self.cfg["hora_irrigacao"]).split(":"))
        if self.ultimo_dia_irrigado != m.date() and (m.hour, m.minute) >= (hh, mm):
            self.ultimo_dia_irrigado = m.date()
            minutos = self.ultima_lamina * self.cfg["area_m2"] / self.cfg["vazao_l_h"] * 60
            self.abrir_valvula(ts, round(minutos, 1), "automatica", None)

    def _virar_dia(self, ts: int) -> None:
        dia = local(ts).date()
        if self.dia_atual is None:
            self.dia_atual = dia
            return
        if dia != self.dia_atual:
            self._fechar_dia(self.dia_atual, ts)
            self.dia_atual = dia
            self.leituras_dia = []
            self.irrigado_dia_mm = 0.0

    def _fechar_dia(self, dia: date, ts: int) -> None:
        cfg = self.cfg
        cultura = self.catalogo.get(cfg["cultura"]) or next(iter(self.catalogo.values()))
        leituras = self.leituras_dia  # zerada a cada virada de dia
        esperadas = 24 * 60 * 60 // self.intervalo_s
        avisos: list[str] = []

        temps = [lt["temp_c"] for lt in leituras]
        tmax, tmin = (max(temps), min(temps)) if temps else (None, None)
        ur = sum(lt["ur_pct"] for lt in leituras) / len(leituras) if leituras else None
        u2 = sum(lt["vento_ms"] for lt in leituras) / len(leituras) if leituras else None
        rs = sum(lt["rad_wm2"] for lt in leituras) * self.intervalo_s / 1e6
        chuva = round(sum(lt["chuva_mm"] for lt in leituras), 1)
        completo = len(leituras) >= 0.8 * esperadas

        ref = date.fromisoformat(cfg["data_referencia"])
        dap = (dia - ref).days
        kc, fase = self._kc(cultura, dap)
        if dap < 0 or dap > cultura["ciclo_dias"]:
            avisos.append(f"fora do ciclo ({dap} dias após a referência)")

        et0 = etc = None
        if completo and None not in (tmax, tmin, ur, u2):
            if FW_ETO is not None:  # mesma função da placa
                j = FW_ETO.dia_do_ano(dia.year, dia.month, dia.day)
                valor = FW_ETO.penman_monteith(
                    tmax, tmin, rs, u2, j, lat=LATITUDE, alt=ALTITUDE_M, ur_media=ur
                )
            else:
                valor = et0_penman_monteith(tmax, tmin, ur, u2, rs, dia)
            et0 = round(valor, 2)
            etc = round(et0 * kc, 2)

        raiz = cfg["raiz_m"] or cultura["raiz_m"]
        taw = round(1000 * cfg["agua_disp"] * raiz, 1)
        irrigacao = round(self.irrigado_dia_mm, 1)
        if etc is not None:
            self.deficit = min(max(self.deficit + etc - chuva - irrigacao, 0.0), taw)

        # Regra simples de balanço (o classificador MLP fica na placa real).
        if not completo:
            classe = None
            avisos.append(f"dia incompleto ({len(leituras)} de {esperadas} leituras): sem classe")
        elif cfg["fonte_irrigacao"] == "nenhuma":
            classe = None
        else:
            classe = 0 if self.deficit < 0.25 * taw else 1 if self.deficit < 0.5 * taw else 2
        self.dias_historico += 1
        if self.dias_historico < HISTORICO_CONFIAVEL_DIAS:
            avisos.append(
                f"histórico com {self.dias_historico} dias (< {HISTORICO_CONFIAVEL_DIAS}): "
                "classe pouco confiável"
            )

        lamina = round(self.deficit / cfg["eficiencia"], 1) if self.deficit >= 0.2 * taw else 0.0
        minutos = round(lamina * cfg["area_m2"] / cfg["vazao_l_h"] * 60, 1)
        n = cfg["n_plantas"]
        consumo = round(etc * cfg["area_m2"], 1) if etc is not None else None
        aplicar = round(lamina * cfg["area_m2"], 1)
        self.ultima_lamina = lamina
        self.seq_diario += 1

        payload = {
            "ts": ts,
            "seq": self.seq_diario,
            "instalacao_id": cfg["instalacao_id"],
            "cfg_v": cfg["cfg_v"],
            "data": dia.isoformat(),
            "cultura": cfg["cultura"],
            "dap": dap,
            "fase": fase,
            "kc": kc,
            "cobertura": 0.98,
            "tmax": tmax,
            "tmin": tmin,
            "ur": round(ur, 1) if ur is not None else None,
            "u2": round(u2, 2) if u2 is not None else None,
            "rs": round(rs, 2),
            "chuva": chuva,
            "irrigacao": irrigacao,
            "et0": et0,
            "etc": etc,
            "taw": taw,
            "deficit": round(self.deficit, 1),
            "classe": classe,
            "lamina_bruta": lamina,
            "minutos": minutos,
            "consumo_l_planta": consumo,
            "consumo_l_total": round(consumo * n, 1) if consumo is not None and n else None,
            "aplicar_l_planta": aplicar,
            "aplicar_l_total": round(aplicar * n, 1) if n else None,
            "avisos": avisos,
        }
        self.publicar("diario", payload)
        self.log(
            f"diário {dia:%d/%m} ET₀={br(et0, 2)} ETc={br(etc, 2)} classe={classe} "
            f"lâmina={br(lamina)} mm ({br(minutos)} min)"
        )

    @staticmethod
    def _kc(cultura: dict[str, Any], dap: int) -> tuple[float, str | None]:
        if FW_CULTURAS is not None:
            try:
                kc, fase, _dentro = FW_CULTURAS.kc_do_dia(cultura["chave"], dap)
                return round(kc, 3), fase
            except ValueError:
                pass  # cultura que só existe no catálogo da plataforma
        fases = cultura.get("fases")
        if fases:
            acumulado = 0
            for fase in fases:
                acumulado += fase["dias"]
                if dap < acumulado:
                    return fase["kc"], fase["chave"]
            return fases[-1]["kc"], fases[-1]["chave"]
        # Uva: Kc por polinômio na placa; aqui uma curva sintética (sem fase).
        ciclo = cultura["ciclo_dias"]
        x = min(max(dap, 0), ciclo) / ciclo
        return round(0.45 + 0.4 * math.sin(math.pi * x), 2), None


# ---------------------------------------------------------------- entrada


def faixa_queda(texto: str | None) -> tuple[int, int] | None:
    if not texto:
        return None
    try:
        ini, fim = texto.split("-")
        h1, m1 = (int(x) for x in ini.split(":"))
        h2, m2 = (int(x) for x in fim.split(":"))
    except ValueError:
        sys.exit("--queda deve ser HH:MM-HH:MM, ex.: 02:00-04:00")
    return h1 * 60 + m1, h2 * 60 + m2


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    env = ler_env()
    parser.add_argument("--serial", action="append", help="repetível (padrão: DISPOSITIVO_SERIAL)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--usuario", help="usuário MQTT (padrão: o próprio serial)")
    parser.add_argument("--senha", action="append", help="uma por --serial (padrão: do .env)")
    parser.add_argument("--intervalo-min", type=int, default=15)
    parser.add_argument(
        "--acelerar", type=float, default=1.0, help="fator de tempo (96 = 1 dia em 15 min)"
    )
    parser.add_argument("--inicio", help="data inicial do histórico simulado, AAAA-MM-DD")
    parser.add_argument("--dias", type=int, help="atalho: --inicio = hoje menos N dias")
    parser.add_argument("--queda", help="janela diária sem rede, HH:MM-HH:MM (hora local)")
    args = parser.parse_args()
    if args.dias and not args.inicio:
        args.inicio = (datetime.now(FUSO).date() - timedelta(days=args.dias)).isoformat()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    seriais = args.serial or [env.get("DISPOSITIVO_SERIAL", "agroedge-00001")]
    senhas = args.senha or []
    if len(senhas) not in (0, len(seriais)):
        sys.exit("informe uma --senha para cada --serial (ou nenhuma, para ler do .env)")
    if not senhas:
        if len(seriais) == 1 and seriais[0] == env.get("DISPOSITIVO_SERIAL"):
            senhas = [env.get("DISPOSITIVO_SENHA", "")]
        else:
            sys.exit("sem senha para os seriais informados: use --senha")

    inicio = None
    if args.inicio:
        d = date.fromisoformat(args.inicio)
        inicio = datetime(d.year, d.month, d.day, tzinfo=FUSO)
        if inicio.timestamp() > time.time():
            sys.exit("--inicio no futuro")
    elif args.acelerar != 1:
        log.warning(
            "--acelerar só tem efeito junto com --inicio (o simulador não passa da hora real)"
        )
    relogio = Relogio(inicio, args.acelerar)
    carregar_firmware()
    catalogo = carregar_catalogo()

    placas: list[Placa] = []
    for serial, senha in zip(seriais, senhas, strict=True):
        cfg = dict(CONFIG_PADRAO, intervalo_telemetria_min=args.intervalo_min)
        placa = Placa(
            serial=serial,
            usuario=args.usuario if args.usuario and len(seriais) == 1 else serial,
            senha=senha,
            inicio_sim=relogio.agora(),
            queda=faixa_queda(args.queda),
            catalogo=catalogo,
            cfg=cfg,
            relogio=relogio.agora,
        )
        placa.conectar(args.host, args.porta)
        placas.append(placa)

    for placa in placas:
        if not placa.conectado.wait(10):
            sys.exit(
                f"[{placa.serial}] não conectou em {args.host}:{args.porta} (broker no ar? senha certa?)"
            )
    time.sleep(1)  # dá tempo de chegar a config retida antes da primeira leitura

    inicio_txt = local(relogio.agora()).strftime("%d/%m/%Y %H:%M")
    log.info(
        "simulando %d placa(s) a partir de %s, fator %sx", len(placas), inicio_txt, relogio.fator
    )
    avisou = False
    try:
        while True:
            agora = relogio.agora()
            for placa in placas:
                placa.avancar(agora)
            if relogio.fator != 1 and relogio.alcancou() and not avisou:
                log.info("histórico alcançou a hora real; seguindo em tempo real")
                avisou = True
            time.sleep(0.05 if not relogio.alcancou() else 1.0)
    except KeyboardInterrupt:
        log.info("encerrando (o broker publica 'offline' pelo LWT só em queda abrupta)")
        for placa in placas:
            if placa.cliente:
                placa.cliente.publish(
                    placa.topico("status"), "offline", qos=1, retain=True
                ).wait_for_publish(2)
                placa.cliente.disconnect()
                placa.cliente.loop_stop()


if __name__ == "__main__":
    main()
