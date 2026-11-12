"""Seed: usuário do .env, token do chatbot, placa padrão, fazenda e cultivo de exemplo.

Idempotente: rodar de novo não duplica nada. Publica a config retida da instalação
de exemplo no broker (se o broker não estiver acessível, só avisa).

Uso (dentro do container):  python -m scripts.seed
"""

import asyncio
import logging
import sys
from datetime import date, timedelta

import aiomqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import gerar_hash_senha, gerar_hash_token
from app.config import obter_settings
from app.db import fabrica_sessao
from app.models import (
    Cultivo,
    Dispositivo,
    EscopoToken,
    Fazenda,
    FonteIrrigacao,
    InicioUso,
    Instalacao,
    TexturaSolo,
    TokenServico,
    Usuario,
    agora_utc,
)
from app.mqtt.publicador import publicar_config
from app.servicos.configuracao import montar_config

log = logging.getLogger("seed")

DIAS_DESDE_FLORACAO = 42  # cai na fase "Queda de frutos" da manga
DIAS_DE_INSTALACAO = 30  # o simulador pode gerar até 30 dias de histórico já atribuído


async def _usuario(sessao: AsyncSession) -> Usuario:
    s = obter_settings()
    if not s.admin_senha:
        sys.exit("ADMIN_SENHA vazio no .env")
    email = s.admin_email.strip().lower()
    usuario = (
        await sessao.execute(select(Usuario).where(Usuario.email == email))
    ).scalar_one_or_none()
    if usuario is None:
        usuario = Usuario(
            nome=s.admin_nome, email=email, senha_hash=gerar_hash_senha(s.admin_senha)
        )
        sessao.add(usuario)
        await sessao.flush()
        log.info("usuário criado: %s", email)
    return usuario


async def _token(sessao: AsyncSession, usuario: Usuario) -> None:
    token = obter_settings().chatbot_token
    if not token:
        log.info("CHATBOT_TOKEN vazio: sem acesso por token")
        return
    token_hash = gerar_hash_token(token)
    existe = (
        await sessao.execute(select(TokenServico).where(TokenServico.token_hash == token_hash))
    ).scalar_one_or_none()
    if existe is None:
        sessao.add(
            TokenServico(
                usuario_id=usuario.id,
                nome="chatbot",
                token_hash=token_hash,
                escopo=EscopoToken.chatbot,
            )
        )
        log.info("token de serviço do chatbot registrado")
    elif existe.escopo != EscopoToken.chatbot:
        existe.escopo = EscopoToken.chatbot
        sessao.add(existe)


async def _dispositivo(sessao: AsyncSession, usuario: Usuario) -> Dispositivo:
    serial = obter_settings().dispositivo_serial
    disp = (
        await sessao.execute(select(Dispositivo).where(Dispositivo.serial == serial))
    ).scalar_one_or_none()
    if disp is None:
        disp = Dispositivo(serial=serial, apelido="Placa da bancada", usuario_id=usuario.id)
        sessao.add(disp)
        await sessao.flush()
        log.info("dispositivo criado: %s", serial)
    elif disp.usuario_id is None:
        disp.usuario_id = usuario.id
        sessao.add(disp)
    return disp


async def _fazenda_e_cultivo(sessao: AsyncSession, usuario: Usuario) -> Cultivo:
    fazenda = (
        await sessao.execute(
            select(Fazenda).where(
                Fazenda.usuario_id == usuario.id, Fazenda.nome == "Fazenda Exemplo"
            )
        )
    ).scalar_one_or_none()
    if fazenda is None:
        fazenda = Fazenda(usuario_id=usuario.id, nome="Fazenda Exemplo", municipio="Petrolina - PE")
        sessao.add(fazenda)
        await sessao.flush()
        log.info("fazenda de exemplo criada")

    cultivo = (
        await sessao.execute(
            select(Cultivo).where(Cultivo.fazenda_id == fazenda.id, Cultivo.exemplo.is_(True))
        )
    ).scalar_one_or_none()
    if cultivo is None:
        cultivo = Cultivo(
            fazenda_id=fazenda.id,
            nome="Pomar 2 · Tommy (exemplo)",
            cultura="manga_tommy_atkins",
            data_referencia=date.today() - timedelta(days=DIAS_DESDE_FLORACAO),
            textura_solo=TexturaSolo.franco_arenoso,
            agua_disp=0.11,
            eficiencia=0.9,
            area_m2=40.0,
            vazao_l_h=64.0,
            fonte_irrigacao=FonteIrrigacao.tempo,
            inicio_uso=InicioUso.meio,
            exemplo=True,
        )
        sessao.add(cultivo)
        await sessao.flush()
        log.info("cultivo de exemplo criado")
    return cultivo


async def _instalacao(sessao: AsyncSession, disp: Dispositivo, cultivo: Cultivo) -> Instalacao:
    ativa = (
        await sessao.execute(
            select(Instalacao).where(Instalacao.dispositivo_id == disp.id, Instalacao.fim.is_(None))
        )
    ).scalar_one_or_none()
    if ativa is not None:
        return ativa
    inst = Instalacao(
        dispositivo_id=disp.id,
        cultivo_id=cultivo.id,
        inicio=agora_utc().replace(hour=0, minute=0, second=0, microsecond=0)
        - timedelta(days=DIAS_DE_INSTALACAO),
        cfg_v=1,
    )
    sessao.add(inst)
    await sessao.flush()
    inst.config_publicada = montar_config(cultivo, inst, disp)
    log.info("instalação criada: %s em %s", disp.serial, cultivo.nome)
    return inst


async def _publicar(serial: str, config: dict) -> None:
    s = obter_settings()
    try:
        async with aiomqtt.Client(
            hostname=s.mqtt_host,
            port=s.mqtt_port,
            username=s.mqtt_usuario,
            password=s.mqtt_senha,
            identifier="plataforma-seed",
        ) as cliente:
            await publicar_config(cliente, serial, config)
        log.info("config publicada (retida) para %s", serial)
    except aiomqtt.MqttError as erro:
        log.warning(
            "não foi possível publicar a config (%s); rode o seed de novo com o broker no ar", erro
        )


async def main() -> None:
    async with fabrica_sessao() as sessao:
        usuario = await _usuario(sessao)
        await _token(sessao, usuario)
        disp = await _dispositivo(sessao, usuario)
        cultivo = await _fazenda_e_cultivo(sessao, usuario)
        inst = await _instalacao(sessao, disp, cultivo)
        await sessao.commit()
        serial, config = disp.serial, inst.config_publicada
    if config:
        await _publicar(serial, config)
    log.info("seed concluído")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if sys.platform == "win32":  # aiomqtt precisa do loop com selector no Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
