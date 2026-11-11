"""Instalar a placa num cultivo (regra 9.3)."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.erros import ErroApp
from app.models import (
    Cultivo,
    Diario,
    Dispositivo,
    Instalacao,
    Irrigacao,
    Leitura,
    datetime_para_ts,
)
from app.mqtt.publicador import Publicador
from app.servicos.configuracao import instalacao_ativa_do_cultivo, publicar_instalacao

log = logging.getLogger("instalacoes")

TOLERANCIA_FUTURO = timedelta(minutes=5)


async def instalar(
    sessao: AsyncSession,
    publicador: Publicador,
    dispositivo: Dispositivo,
    cultivo: Cultivo,
    inicio: datetime | None,
    agora: datetime,
) -> Instalacao:
    """Fecha a instalação ativa, cria a nova, publica a config e reatribui o que veio depois."""
    # Os ts da placa são em segundos: sem isso, uma leitura do mesmo segundo ficaria de fora.
    inicio = (inicio or agora).replace(microsecond=0)
    if cultivo.arquivado:
        raise ErroApp(409, "cultivo_arquivado", "Este cultivo está arquivado.")
    if inicio > agora + TOLERANCIA_FUTURO:
        raise ErroApp(400, "inicio_no_futuro", "O início da instalação não pode estar no futuro.")

    ocupante = await instalacao_ativa_do_cultivo(sessao, cultivo.id)  # type: ignore[arg-type]
    if ocupante is not None:
        if ocupante.dispositivo_id == dispositivo.id:
            raise ErroApp(409, "ja_instalada", "A placa já está instalada neste cultivo.")
        raise ErroApp(
            409, "cultivo_ocupado", "Este cultivo já tem outra placa instalada. Mova-a antes."
        )

    anteriores = (
        (
            await sessao.execute(
                select(Instalacao).where(col(Instalacao.dispositivo_id) == dispositivo.id)
            )
        )
        .scalars()
        .all()
    )
    ativa = next((i for i in anteriores if i.fim is None), None)
    # Os períodos de uma placa não se sobrepõem.
    limite = max(
        [i.fim for i in anteriores if i.fim is not None] + ([ativa.inicio] if ativa else []),
        default=None,
    )
    if limite is not None and inicio <= limite:
        raise ErroApp(
            409,
            "periodo_sobreposto",
            "O início precisa ser depois do início da instalação atual da placa "
            "(e do fim das anteriores).",
        )

    if ativa is not None:
        ativa.fim = inicio
        sessao.add(ativa)
        await sessao.flush()  # libera a restrição "uma instalação ativa por placa"

    nova = Instalacao(
        dispositivo_id=dispositivo.id,  # type: ignore[arg-type]
        cultivo_id=cultivo.id,  # type: ignore[arg-type]
        inicio=inicio,
        cfg_v=1,
    )
    sessao.add(nova)
    await sessao.flush()

    reatribuidas = await reatribuir(sessao, dispositivo.id, nova.id, datetime_para_ts(inicio))  # type: ignore[arg-type]
    await publicar_instalacao(sessao, publicador, nova, cultivo)
    log.info(
        "instalacao serial=%s cultivo=%s inicio=%s reatribuidas=%s",
        dispositivo.serial,
        cultivo.id,
        inicio,
        reatribuidas,
    )
    return nova


async def reatribuir(
    sessao: AsyncSession, dispositivo_id: int, instalacao_id: int, desde_ts: int
) -> dict[str, int]:
    """Leituras, diários e irrigações da placa com ts ≥ início passam para a nova instalação."""
    contagem = {}
    for nome, modelo, coluna in (
        ("leituras", Leitura, Leitura.ts),
        ("diarios", Diario, Diario.ts),
        ("irrigacoes", Irrigacao, Irrigacao.ts_inicio),
    ):
        resultado = await sessao.execute(
            update(modelo)  # type: ignore[arg-type]
            .where(
                col(modelo.dispositivo_id) == dispositivo_id,  # type: ignore[attr-defined]
                col(coluna) >= desde_ts,
            )
            .values(instalacao_id=instalacao_id)
        )
        contagem[nome] = resultado.rowcount  # type: ignore[attr-defined]
    return contagem
