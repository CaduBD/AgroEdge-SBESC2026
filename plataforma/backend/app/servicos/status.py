"""Status do dispositivo para a pill do topo (regra 9.6)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.models import Dispositivo, Leitura, StatusMqtt, ts_para_datetime

EstadoPill = Literal["ao_vivo", "atrasado", "sem_contato", "sincronizando"]
SEM_CONTATO_APOS = timedelta(hours=1)


@dataclass
class StatusPill:
    estado: EstadoPill
    ultima_telemetria: datetime | None
    sincronizando: int  # leituras ainda no buffer da placa


def status_dispositivo(disp: Dispositivo, ultima: Leitura | None, agora: datetime) -> StatusPill:
    ultima_ts = ts_para_datetime(ultima.ts) if ultima else None
    buf = (ultima.buf or 0) if ultima else 0
    sem_mensagem = disp.ultimo_contato is None or agora - disp.ultimo_contato > SEM_CONTATO_APOS

    if disp.status_mqtt == StatusMqtt.offline or sem_mensagem:
        estado: EstadoPill = "sem_contato"
    elif buf > 0:
        estado = "sincronizando"
    elif (
        disp.status_mqtt == StatusMqtt.online
        and ultima_ts is not None
        and agora - ultima_ts < timedelta(minutes=2 * disp.intervalo_telemetria_min)
    ):
        estado = "ao_vivo"
    else:
        estado = "atrasado"
    return StatusPill(estado, ultima_ts, buf if estado == "sincronizando" else 0)
