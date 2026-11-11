"""Peças compartilhadas pelas rotas: publicador, conversões para as saídas."""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models import Cultivo, Diario, Dispositivo, Instalacao
from app.mqtt.publicador import Publicador
from app.schemas.api import ConfiguracaoPlaca, CultivoSaida, InstalacaoSaida
from app.servicos.configuracao import avisos_cultivo, instalacao_ativa_do_cultivo, taw_raw
from app.tempo import hoje_local


def obter_publicador(request: Request) -> Publicador:
    return request.app.state.publicador


PublicadorDep = Annotated[Publicador, Depends(obter_publicador)]


async def cultivo_saida(sessao: AsyncSession, cultivo: Cultivo, agora: datetime) -> CultivoSaida:
    taw, raw = taw_raw(cultivo)
    configuracao = None
    instalacao = await instalacao_ativa_do_cultivo(sessao, cultivo.id)  # type: ignore[arg-type]
    if instalacao is not None:
        disp = await sessao.get(Dispositivo, instalacao.dispositivo_id)
        configuracao = ConfiguracaoPlaca(
            serial=disp.serial if disp else "?",
            instalacao_id=instalacao.id,  # type: ignore[arg-type]
            cfg_v=instalacao.cfg_v,
            cfg_v_aplicada=instalacao.cfg_v_aplicada,
            aplicada=instalacao.cfg_v_aplicada == instalacao.cfg_v,
        )
    ultima_classe = (
        await sessao.execute(
            select(Diario.classe)
            .join(Instalacao, col(Instalacao.id) == col(Diario.instalacao_id))
            .where(col(Instalacao.cultivo_id) == cultivo.id)
            .order_by(col(Diario.data).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return CultivoSaida.model_validate(
        {
            **cultivo.model_dump(),
            "taw_mm": taw,
            "raw_mm": raw,
            "dia_do_ciclo": (hoje_local(agora) - cultivo.data_referencia).days,
            "ultima_classe": ultima_classe,
            "configuracao": configuracao,
            "avisos": avisos_cultivo(cultivo),
        }
    )


async def instalacao_saida(sessao: AsyncSession, inst: Instalacao) -> InstalacaoSaida:
    disp = await sessao.get(Dispositivo, inst.dispositivo_id)
    cultivo = await sessao.get(Cultivo, inst.cultivo_id)
    return InstalacaoSaida.model_validate(
        {
            **inst.model_dump(),
            "serial": disp.serial if disp else "?",
            "cultivo_nome": cultivo.nome if cultivo else "?",
        }
    )
