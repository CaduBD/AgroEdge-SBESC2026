"""Ouvinte do SSE da plataforma (CHATBOT.md, seção 5).

- Lê `GET /api/stream` com o token e entrega cada evento (menos `ping`) a um callback.
- Sem receber nada por ~70 s (nem `ping`, que vem a cada 25 s), considera a conexão morta
  e reconecta.
- Eventos perdidos enquanto estava desconectado não voltam: depois de cada reconexão
  chama `ao_reconectar`, para quem usa o bot consultar o `/resumo` de novo.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("sse")

TIMEOUT_LEITURA_S = 70
ESPERA_INICIAL_S = 3.0
ESPERA_MAXIMA_S = 60.0


@dataclass
class EventoSse:
    tipo: str
    dados: dict[str, Any] = field(default_factory=dict)

    @property
    def serial(self) -> str | None:
        valor = self.dados.get("serial")
        return str(valor) if valor is not None else None

    @property
    def cultivo_id(self) -> int | None:
        valor = self.dados.get("cultivo_id")
        return int(valor) if valor is not None else None


class LeitorSse:
    """Monta eventos a partir das linhas do stream (formato text/event-stream)."""

    def __init__(self) -> None:
        self._tipo: str | None = None
        self._dados: list[str] = []
        self.retry_ms: int | None = None

    def linha(self, texto: str) -> EventoSse | None:
        """Recebe uma linha (sem o \\n). Devolve um evento quando ele termina (linha vazia)."""
        if texto == "":
            return self._despachar()
        if texto.startswith(":"):
            return None  # comentário (": conectado")
        campo, _, valor = texto.partition(":")
        valor = valor.removeprefix(" ")
        if campo == "event":
            self._tipo = valor
        elif campo == "data":
            self._dados.append(valor)
        elif campo == "retry" and valor.isdigit():
            self.retry_ms = int(valor)
        return None

    def _despachar(self) -> EventoSse | None:
        tipo, dados = self._tipo or "message", "\n".join(self._dados)
        self._tipo, self._dados = None, []
        if not dados:
            return None
        try:
            corpo = json.loads(dados)
        except json.JSONDecodeError:
            log.warning("sse dado que não é JSON tipo=%s", tipo)
            return None
        return EventoSse(tipo, corpo if isinstance(corpo, dict) else {"valor": corpo})


CONECTADO = "_conectado"  # pseudo-evento: a conexão abriu (antes de qualquer evento real)


async def eventos(
    url: str, cabecalhos: dict[str, str], transporte: httpx.AsyncBaseTransport | None = None
) -> AsyncIterator[EventoSse]:
    """Uma conexão: gera os eventos até ela cair (levanta exceção) ou o servidor fechar."""
    timeout = httpx.Timeout(TIMEOUT_LEITURA_S, connect=10)
    async with (
        httpx.AsyncClient(timeout=timeout, transport=transporte) as http,
        http.stream("GET", url, headers={**cabecalhos, "Accept": "text/event-stream"}) as r,
    ):
        if r.status_code == 401:
            raise PermissionError("token recusado pela plataforma (401)")
        r.raise_for_status()
        yield EventoSse(CONECTADO)
        leitor = LeitorSse()
        async for linha in r.aiter_lines():
            evento = leitor.linha(linha.rstrip("\r"))
            if evento is not None:
                yield evento


async def ouvir_para_sempre(
    url: str,
    cabecalhos: dict[str, str],
    ao_evento: Callable[[EventoSse], Awaitable[None]],
    ao_reconectar: Callable[[], Awaitable[None]] | None = None,
    transporte: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Fica conectado ao SSE, reconectando com espera crescente quando a conexão cai.

    `ao_reconectar` roda logo depois de cada reconexão (não na primeira conexão): é a hora
    de buscar pela API o que pode ter chegado enquanto o bot estava desconectado.
    """
    espera = ESPERA_INICIAL_S
    ja_conectou = False
    while True:
        try:
            log.info("sse conectando url=%s", url)
            async for evento in eventos(url, cabecalhos, transporte):
                if evento.tipo == CONECTADO:
                    log.info("sse conectado")
                    espera = ESPERA_INICIAL_S
                    if ja_conectou and ao_reconectar is not None:
                        await _proteger(ao_reconectar(), "recuperar eventos perdidos")
                    ja_conectou = True
                elif evento.tipo != "ping":
                    await _proteger(ao_evento(evento), f"tratar evento {evento.tipo}")
            log.warning("sse servidor fechou a conexão")
        except asyncio.CancelledError:
            raise
        except PermissionError as erro:
            log.error("sse %s: confira o AGROEDGE_TOKEN", erro)
            espera = ESPERA_MAXIMA_S
        except (httpx.HTTPError, OSError) as erro:
            log.warning(
                "sse conexão caiu (%s); nova tentativa em %.0f s", type(erro).__name__, espera
            )
        await asyncio.sleep(espera)
        espera = min(espera * 2, ESPERA_MAXIMA_S)


async def _proteger(tarefa: Awaitable[None], o_que: str) -> None:
    """Um evento com problema não derruba o ouvinte."""
    try:
        await tarefa
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("sse erro ao %s", o_que)
