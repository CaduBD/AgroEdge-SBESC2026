"""SSE: eventos ao vivo (seção 11). Só repassa eventos de recursos do usuário."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from sqlmodel import col, select
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.auth import UsuarioAtual
from app.db import fabrica_sessao
from app.eventos import Evento, barramento
from app.models import Cultivo, Dispositivo, Fazenda

rotas = APIRouter(prefix="/api", tags=["tempo real"])

PING_S = 25
RECONEXAO_MS = 3000


async def _pertence(usuario_id: int, evento: Evento) -> bool:
    """Mesma regra de posse da API: a placa ou o cultivo do evento é do usuário."""
    async with fabrica_sessao() as sessao:
        dono_placa = (
            await sessao.execute(
                select(Dispositivo.usuario_id).where(col(Dispositivo.serial) == evento.serial)
            )
        ).scalar_one_or_none()
        if dono_placa == usuario_id:
            return True
        if evento.cultivo_id is None:
            return False
        dono_cultivo = (
            await sessao.execute(
                select(Fazenda.usuario_id)
                .join(Cultivo, col(Cultivo.fazenda_id) == col(Fazenda.id))
                .where(col(Cultivo.id) == evento.cultivo_id)
            )
        ).scalar_one_or_none()
        return dono_cultivo == usuario_id


@rotas.get(
    "/stream",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream(request: Request, usuario: UsuarioAtual) -> EventSourceResponse:
    """Server-Sent Events. Eventos: `leitura`, `diario`, `irrigacao`, `status`,
    `config_aplicada`, `comando`. Cada `data` é JSON com `serial`, `cultivo_id` e os
    dados do evento. A cada 25 s chega um evento `ping` (sem dados): se o cliente ficar
    mais de ~60 s sem receber nada, a conexão caiu e ele deve reconectar."""
    usuario_id: int = usuario.id  # type: ignore[assignment]
    fila = barramento.assinar()

    async def gerar() -> AsyncIterator[ServerSentEvent | dict[str, str]]:
        try:
            # Primeiro envio imediato: proxies (Vite, Node, Caddy) só repassam os cabeçalhos
            # junto com o primeiro dado; sem isto o navegador fica "conectando" até o primeiro
            # evento ou ping. O `retry` diz ao navegador em quanto tempo reconectar.
            yield ServerSentEvent(comment="conectado", retry=RECONEXAO_MS)
            while True:
                evento = await fila.get()
                if await request.is_disconnected():
                    break
                if not await _pertence(usuario_id, evento):
                    continue
                yield {
                    "event": evento.tipo,
                    "data": json.dumps(
                        {"serial": evento.serial, "cultivo_id": evento.cultivo_id, **evento.dados},
                        ensure_ascii=False,
                        default=str,
                    ),
                }
        finally:
            barramento.cancelar(fila)

    # Ping como evento nomeado (não comentário), para o painel enxergá-lo: se passar muito
    # tempo sem nada chegar, o painel reconecta (protege de conexões "zumbi" atrás de proxies).
    return EventSourceResponse(
        gerar(),
        ping=PING_S,
        ping_message_factory=lambda: ServerSentEvent(event="ping", data="{}"),
    )
