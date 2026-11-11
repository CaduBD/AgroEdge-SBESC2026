"""Publica `config` (retida) e `cmd` (nunca retido) para a placa.

`Publicador` usa o cliente MQTT do ingestor (uma só conexão do backend com o broker).
Os serviços recebem um `Publicador`; nos testes entra um falso que só registra.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import aiomqtt

from app.erros import ErroApp

log = logging.getLogger("publicador")


def topico(serial: str, tipo: str) -> str:
    return f"agroedge/{serial}/{tipo}"


async def publicar_config(cliente: aiomqtt.Client, serial: str, config: dict[str, Any]) -> None:
    await cliente.publish(
        topico(serial, "config"), json.dumps(config, ensure_ascii=False), qos=1, retain=True
    )
    log.info("publicador config serial=%s cfg_v=%s", serial, config.get("cfg_v"))


async def publicar_comando(cliente: aiomqtt.Client, serial: str, comando: dict[str, Any]) -> None:
    await cliente.publish(topico(serial, "cmd"), json.dumps(comando), qos=1, retain=False)
    log.info("publicador cmd serial=%s id=%s acao=%s", serial, comando["id"], comando["acao"])


class SemBroker(ErroApp):
    def __init__(self) -> None:
        super().__init__(
            503, "sem_broker", "A plataforma está sem conexão com o broker MQTT. Tente de novo."
        )


class Publicador:
    def __init__(self, obter_cliente: Callable[[], aiomqtt.Client | None]) -> None:
        self._obter_cliente = obter_cliente

    def _cliente(self) -> aiomqtt.Client:
        cliente = self._obter_cliente()
        if cliente is None:
            raise SemBroker()
        return cliente

    async def config(self, serial: str, config: dict[str, Any]) -> None:
        try:
            await publicar_config(self._cliente(), serial, config)
        except aiomqtt.MqttError as erro:
            raise SemBroker() from erro

    async def comando(self, serial: str, comando: dict[str, Any]) -> None:
        try:
            await publicar_comando(self._cliente(), serial, comando)
        except aiomqtt.MqttError as erro:
            raise SemBroker() from erro
