"""Payloads MQTT (seção 7.3). Campos desconhecidos são ignorados; obrigatórios ausentes falham."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TelemetriaPayload(_Base):
    ts: int
    seq: int
    instalacao_id: int | None = None
    cfg_v: int | None = None
    temp_c: float | None = None
    ur_pct: float | None = None
    vento_ms: float | None = None
    rad_wm2: float | None = None
    chuva_mm: float | None = None
    rssi: int | None = None
    bat_v: float | None = None
    buf: int | None = None


class DiarioPayload(_Base):
    ts: int
    seq: int
    instalacao_id: int | None = None
    cfg_v: int | None = None
    data: date
    cultura: str | None = None
    dap: int | None = None
    fase: str | None = None
    kc: float | None = None
    cobertura: float | None = None
    tmax: float | None = None
    tmin: float | None = None
    ur: float | None = None
    u2: float | None = None
    rs: float | None = None
    chuva: float | None = None
    irrigacao: float | None = None
    et0: float | None = None
    etc: float | None = None
    taw: float | None = None
    deficit: float | None = None
    classe: Literal[0, 1, 2] | None = None
    lamina_bruta: float | None = None
    minutos: float | None = None
    consumo_l_planta: float | None = None
    consumo_l_total: float | None = None
    aplicar_l_planta: float | None = None
    aplicar_l_total: float | None = None
    avisos: list[str] = Field(default_factory=list)


class IrrigacaoPayload(_Base):
    id: str = Field(min_length=1, max_length=100)
    ts_inicio: int
    ts_fim: int | None = None
    minutos: float | None = None
    mm: float | None = None
    origem: Literal["automatica", "manual"]
    cmd_id: str | None = None
    estado: Literal["iniciada", "concluida", "cancelada", "interrompida"]


class CmdRespPayload(_Base):
    id: str = Field(min_length=1, max_length=100)
    ts: int
    resultado: Literal[
        "executado",
        "recusado_vencido",
        "recusado_em_andamento",
        "cancelado",
        "recusado_invalido",
    ]


class ConfigPayload(_Base):
    """Configuração enviada à placa (retida)."""

    cfg_v: int
    instalacao_id: int
    cultura: str
    data_referencia: str  # YYYY-MM-DD
    agua_disp: float
    raiz_m: float | None
    eficiencia: float
    area_m2: float
    vazao_l_h: float
    n_plantas: int | None
    fonte_irrigacao: str
    inicio_uso: str
    irrigacao_automatica: bool
    hora_irrigacao: str  # HH:MM
    intervalo_telemetria_min: int


class CmdPayload(_Base):
    """Comando manual da válvula (nunca retido)."""

    id: str
    acao: Literal["abrir", "cancelar"]
    minutos: float | None = None
    valido_ate: int
