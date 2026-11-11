"""Barramento interno de eventos em memória (alimenta o SSE, seção 11)."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger(__name__)

TipoEvento = Literal["leitura", "diario", "irrigacao", "status", "config_aplicada", "comando"]


@dataclass
class Evento:
    tipo: TipoEvento
    serial: str
    cultivo_id: int | None = None
    dados: dict[str, Any] = field(default_factory=dict)


class Barramento:
    """Uma fila por cliente conectado. Cliente lento perde eventos (não trava o ingestor)."""

    def __init__(self, tamanho_fila: int = 100) -> None:
        self._filas: set[asyncio.Queue[Evento]] = set()
        self._tamanho = tamanho_fila

    def assinar(self) -> asyncio.Queue[Evento]:
        fila: asyncio.Queue[Evento] = asyncio.Queue(maxsize=self._tamanho)
        self._filas.add(fila)
        return fila

    def cancelar(self, fila: asyncio.Queue[Evento]) -> None:
        self._filas.discard(fila)

    def publicar(self, evento: Evento) -> None:
        for fila in list(self._filas):
            try:
                fila.put_nowait(evento)
            except asyncio.QueueFull:
                log.warning("eventos fila cheia, evento descartado tipo=%s", evento.tipo)


barramento = Barramento()
