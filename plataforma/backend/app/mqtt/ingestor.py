"""Ingestor MQTT: assina os tópicos da placa, valida, grava e emite eventos.

Roda como tarefa no lifespan do FastAPI. Reconecta sozinho se o broker cair.
"""

import asyncio
import logging
import ssl

import aiomqtt
from sqlmodel import col, select

from app.config import Settings
from app.db import fabrica_sessao
from app.eventos import barramento
from app.models import Dispositivo, Instalacao
from app.mqtt.publicador import publicar_config
from app.servicos.ingestao import TIPOS, processar_mensagem

log = logging.getLogger("ingestor")

ESPERA_RECONEXAO_S = 5


class Ingestor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cliente: aiomqtt.Client | None = None  # usado pelo publicador quando conectado

    def _novo_cliente(self) -> aiomqtt.Client:
        s = self.settings
        return aiomqtt.Client(
            hostname=s.mqtt_host,
            port=s.mqtt_port,
            username=s.mqtt_usuario,
            password=s.mqtt_senha,
            identifier="plataforma",
            clean_session=False,
            keepalive=60,
            tls_context=ssl.create_default_context() if s.mqtt_tls else None,
        )

    async def rodar(self) -> None:
        while True:
            try:
                async with self._novo_cliente() as cliente:
                    self.cliente = cliente
                    for tipo in TIPOS:
                        await cliente.subscribe(f"agroedge/+/{tipo}", qos=1)
                    await self._republicar_configs(cliente)
                    log.info(
                        "ingestor conectado host=%s porta=%s",
                        self.settings.mqtt_host,
                        self.settings.mqtt_port,
                    )
                    async for mensagem in cliente.messages:
                        await self._tratar(str(mensagem.topic), mensagem.payload)
            except aiomqtt.MqttError as erro:
                log.warning(
                    "ingestor sem broker (%s); nova tentativa em %ds", erro, ESPERA_RECONEXAO_S
                )
            finally:
                self.cliente = None
            await asyncio.sleep(ESPERA_RECONEXAO_S)

    async def _republicar_configs(self, cliente: aiomqtt.Client) -> None:
        """Republica (retida) a config de toda instalação ativa. Cobre o caso de uma config
        salva enquanto o broker estava fora; para a placa, reaplicar a mesma versão é inócuo."""
        async with fabrica_sessao() as sessao:
            linhas = (
                await sessao.execute(
                    select(Dispositivo.serial, Instalacao.config_publicada)
                    .join(Instalacao, col(Instalacao.dispositivo_id) == col(Dispositivo.id))
                    .where(
                        col(Instalacao.fim).is_(None), col(Instalacao.config_publicada).is_not(None)
                    )
                )
            ).all()
        for serial, config in linhas:
            await publicar_config(cliente, serial, config)

    async def _tratar(self, topico: str, payload: object) -> None:
        dados = payload if isinstance(payload, bytes) else str(payload or "").encode()
        try:
            async with fabrica_sessao() as sessao:
                eventos = await processar_mensagem(sessao, topico, dados)
        except Exception:  # não deixa uma mensagem ruim derrubar o ingestor
            log.exception("ingestor erro ao processar topico=%s", topico)
            return
        for evento in eventos:
            barramento.publicar(evento)
