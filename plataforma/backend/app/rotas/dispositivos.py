"""Placas: status, instalação num cultivo (regra 9.3) e comandos da válvula (regra 9.5)."""

from datetime import UTC
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import col, select

from app.auth import DispositivoDoUsuario, Sessao, UsuarioAtual, cultivo_do_usuario
from app.config import obter_settings
from app.models import (
    Comando,
    Dispositivo,
    Instalacao,
    Leitura,
    MensagemRejeitada,
    agora_utc,
)
from app.rotas.comum import PublicadorDep, instalacao_saida
from app.schemas.api import (
    ComandoEntrada,
    ComandoSaida,
    ConexaoPlaca,
    DispositivoDetalhe,
    DispositivoEdicao,
    DispositivoSaida,
    InstalacaoSaida,
    InstalarEntrada,
)
from app.servicos.comandos import criar_comando
from app.servicos.configuracao import reconfigurar_dispositivo
from app.servicos.consultas import ultima_leitura_do_dispositivo
from app.servicos.instalacoes import instalar
from app.servicos.status import status_dispositivo

rotas = APIRouter(prefix="/api/dispositivos", tags=["dispositivos"])

N_REJEITADAS = 20
N_COMANDOS = 20


async def _saida(sessao: Sessao, disp: Dispositivo) -> dict[str, Any]:
    ultima = await ultima_leitura_do_dispositivo(sessao, disp.id)  # type: ignore[arg-type]
    status = status_dispositivo(disp, ultima, agora_utc())
    ativa = (
        await sessao.execute(
            select(Instalacao).where(
                col(Instalacao.dispositivo_id) == disp.id, col(Instalacao.fim).is_(None)
            )
        )
    ).scalar_one_or_none()
    return {
        **disp.model_dump(),
        "status": status.estado,
        "sincronizando": status.sincronizando,
        "ultima_telemetria": status.ultima_telemetria,
        "bat_v": ultima.bat_v if ultima else None,
        "rssi": ultima.rssi if ultima else None,
        "buf": ultima.buf if ultima else None,
        "instalacao": await instalacao_saida(sessao, ativa) if ativa else None,
    }


@rotas.get("", response_model=list[DispositivoSaida])
async def listar(usuario: UsuarioAtual, sessao: Sessao) -> list[dict[str, Any]]:
    dispositivos = (
        await sessao.execute(
            select(Dispositivo)
            .where(col(Dispositivo.usuario_id) == usuario.id)
            .order_by(col(Dispositivo.serial))
        )
    ).scalars()
    return [await _saida(sessao, d) for d in dispositivos]


@rotas.get("/{serial}", response_model=DispositivoDetalhe)
async def detalhe(disp: DispositivoDoUsuario, sessao: Sessao) -> dict[str, Any]:
    sem_cultivo = (
        await sessao.execute(
            select(func.count())
            .select_from(Leitura)
            .where(col(Leitura.dispositivo_id) == disp.id, col(Leitura.instalacao_id).is_(None))
        )
    ).scalar_one()
    rejeitadas = (
        (
            await sessao.execute(
                select(MensagemRejeitada)
                .where(col(MensagemRejeitada.topico).startswith(f"agroedge/{disp.serial}/"))
                .order_by(col(MensagemRejeitada.id).desc())
                .limit(N_REJEITADAS)
            )
        )
        .scalars()
        .all()
    )
    settings = obter_settings()
    return {
        **await _saida(sessao, disp),
        "leituras_sem_cultivo": sem_cultivo,
        "rejeitadas": rejeitadas,
        "conexao": ConexaoPlaca(
            mqtt_host=settings.broker_host_publico,
            mqtt_porta=settings.broker_porta_publica or settings.mqtt_port,
            mqtt_tls=settings.broker_tls_publico,
            mqtt_usuario=disp.serial,
        ),
    }


@rotas.patch("/{serial}", response_model=DispositivoDetalhe)
async def editar(
    entrada: DispositivoEdicao,
    disp: DispositivoDoUsuario,
    sessao: Sessao,
    publicador: PublicadorDep,
) -> dict[str, Any]:
    """Muda o apelido ou o intervalo de telemetria. Com a placa instalada, um intervalo novo
    gera nova versão da config (a placa confirma na próxima telemetria)."""
    dados = entrada.model_dump(exclude_unset=True)
    if "apelido" in dados:
        disp.apelido = (dados["apelido"] or "").strip() or None
    novo = dados.get("intervalo_telemetria_min")
    if novo is not None and novo != disp.intervalo_telemetria_min:
        disp.intervalo_telemetria_min = novo
        sessao.add(disp)
        await reconfigurar_dispositivo(sessao, publicador, disp)
    sessao.add(disp)
    await sessao.commit()
    return await detalhe(disp, sessao)


@rotas.post("/{serial}/instalar", response_model=InstalacaoSaida, status_code=201)
async def instalar_em_cultivo(
    entrada: InstalarEntrada,
    disp: DispositivoDoUsuario,
    usuario: UsuarioAtual,
    sessao: Sessao,
    publicador: PublicadorDep,
) -> InstalacaoSaida:
    """Instala a placa num cultivo. Com início no passado, as leituras desde então mudam
    para o novo cultivo."""
    cultivo = await cultivo_do_usuario(sessao, usuario, entrada.cultivo_id)
    inicio = entrada.inicio
    if inicio is not None and inicio.tzinfo is not None:
        inicio = inicio.astimezone(UTC).replace(tzinfo=None)
    nova = await instalar(sessao, publicador, disp, cultivo, inicio, agora_utc())
    await sessao.commit()
    return await instalacao_saida(sessao, nova)


@rotas.get("/{serial}/instalacoes", response_model=list[InstalacaoSaida])
async def instalacoes(disp: DispositivoDoUsuario, sessao: Sessao) -> list[InstalacaoSaida]:
    lista = (
        await sessao.execute(
            select(Instalacao)
            .where(col(Instalacao.dispositivo_id) == disp.id)
            .order_by(col(Instalacao.inicio).desc())
        )
    ).scalars()
    return [await instalacao_saida(sessao, i) for i in lista]


@rotas.post("/{serial}/comandos", response_model=ComandoSaida, status_code=201)
async def enviar_comando(
    entrada: ComandoEntrada,
    disp: DispositivoDoUsuario,
    usuario: UsuarioAtual,
    sessao: Sessao,
    publicador: PublicadorDep,
) -> Comando:
    """Abre (por N minutos) ou fecha a válvula. Válido por 10 minutos; a resposta da placa
    chega pelo SSE (evento `comando`) e aparece em GET .../comandos."""
    return await criar_comando(
        sessao, publicador, disp, usuario, entrada.acao, entrada.minutos, agora_utc()
    )


@rotas.get("/{serial}/comandos", response_model=list[ComandoSaida])
async def comandos(disp: DispositivoDoUsuario, sessao: Sessao) -> list[Comando]:
    return list(
        (
            await sessao.execute(
                select(Comando)
                .where(col(Comando.dispositivo_id) == disp.id)
                .order_by(col(Comando.criado_em).desc())
                .limit(N_COMANDOS)
            )
        ).scalars()
    )
