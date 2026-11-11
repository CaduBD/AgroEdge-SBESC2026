"""Comandos manuais da válvula (regra 9.5)."""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.erros import ErroApp
from app.eventos import Evento
from app.models import (
    AcaoComando,
    Comando,
    Dispositivo,
    EstadoComando,
    Instalacao,
    StatusMqtt,
    Usuario,
    datetime_para_ts,
)
from app.mqtt.publicador import Publicador, SemBroker

log = logging.getLogger("comandos")

VALIDADE = timedelta(minutes=10)
OFFLINE_TOLERADO = timedelta(minutes=10)
MINUTOS_MIN, MINUTOS_MAX = 1, 120


async def criar_comando(
    sessao: AsyncSession,
    publicador: Publicador,
    dispositivo: Dispositivo,
    usuario: Usuario,
    acao: AcaoComando,
    minutos: float | None,
    agora: datetime,
) -> Comando:
    if acao == AcaoComando.abrir:
        if minutos is None or not MINUTOS_MIN <= minutos <= MINUTOS_MAX:
            raise ErroApp(
                400,
                "minutos_invalidos",
                f"Informe de {MINUTOS_MIN} a {MINUTOS_MAX} minutos para abrir a válvula.",
            )
    else:
        minutos = None

    sem_contato_recente = (
        dispositivo.ultimo_contato is None or agora - dispositivo.ultimo_contato > OFFLINE_TOLERADO
    )
    if dispositivo.status_mqtt != StatusMqtt.online and sem_contato_recente:
        raise ErroApp(
            409,
            "dispositivo_offline",
            "A placa está sem contato há mais de 10 minutos: o comando não chegaria a tempo.",
        )

    comando = Comando(
        id=str(uuid.uuid4()),
        dispositivo_id=dispositivo.id,  # type: ignore[arg-type]
        usuario_id=usuario.id,  # type: ignore[arg-type]
        acao=acao,
        minutos=minutos,
        criado_em=agora,
        valido_ate=agora + VALIDADE,
    )
    payload: dict[str, object] = {
        "id": comando.id,
        "acao": acao.value,
        "valido_ate": datetime_para_ts(comando.valido_ate),
    }
    if minutos is not None:
        payload["minutos"] = minutos
    # Grava antes de publicar: a resposta da placa pode chegar antes do fim desta função.
    sessao.add(comando)
    await sessao.commit()
    try:
        await publicador.comando(dispositivo.serial, payload)
    except SemBroker:
        await sessao.delete(comando)  # não foi enviado: não fica no histórico
        await sessao.commit()
        raise
    return comando


async def expirar_comandos(sessao: AsyncSession, agora: datetime) -> list[Evento]:
    """Comandos `enviado` vencidos viram `expirado`. Roda a cada minuto."""
    vencidos = (
        await sessao.execute(
            select(Comando, Dispositivo)
            .join(Dispositivo, col(Dispositivo.id) == col(Comando.dispositivo_id))
            .where(col(Comando.estado) == EstadoComando.enviado, col(Comando.valido_ate) < agora)
        )
    ).all()
    eventos = []
    for comando, disp in vencidos:
        comando.estado = EstadoComando.expirado
        sessao.add(comando)
        ativa = (
            await sessao.execute(
                select(Instalacao).where(
                    col(Instalacao.dispositivo_id) == disp.id, col(Instalacao.fim).is_(None)
                )
            )
        ).scalar_one_or_none()
        eventos.append(
            Evento(
                "comando",
                disp.serial,
                ativa.cultivo_id if ativa else None,
                {"id": comando.id, "estado": "expirado", "resultado": None},
            )
        )
        log.info("comando expirado serial=%s id=%s", disp.serial, comando.id)
    await sessao.commit()
    return eventos
