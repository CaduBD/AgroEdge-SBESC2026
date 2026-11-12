import asyncio

import httpx
import pytest

from agroedge_bot.nucleo import sse
from agroedge_bot.nucleo.sse import EventoSse, LeitorSse


def ler(linhas: list[str]) -> list[EventoSse]:
    leitor = LeitorSse()
    return [e for linha in linhas if (e := leitor.linha(linha)) is not None]


def test_leitor_formato_da_plataforma() -> None:
    eventos = ler(
        [
            ": conectado",
            "retry: 3000",
            "",
            "event: diario",
            'data: {"serial": "agroedge-00001", "cultivo_id": 2, "data": "2026-11-10", "classe": 0}',
            "",
            "event: ping",
            "data: {}",
            "",
        ]
    )
    assert [e.tipo for e in eventos] == ["diario", "ping"]
    assert eventos[0].serial == "agroedge-00001"
    assert eventos[0].cultivo_id == 2
    assert eventos[0].dados["data"] == "2026-11-10"


def test_leitor_data_em_varias_linhas_e_lixo() -> None:
    eventos = ler(["event: x", 'data: {"a":', "data: 1}", "", "event: y", "data: não é json", ""])
    assert len(eventos) == 1 and eventos[0].dados == {"a": 1}


def test_leitor_guarda_retry() -> None:
    leitor = LeitorSse()
    leitor.linha("retry: 3000")
    assert leitor.retry_ms == 3000


async def test_reconecta_e_recupera(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sse, "ESPERA_INICIAL_S", 0.01)
    conexoes = 0

    def responder(req: httpx.Request) -> httpx.Response:
        nonlocal conexoes
        conexoes += 1
        assert req.headers["Authorization"] == "Bearer t"
        corpo = (
            ": conectado\nretry: 3000\n\n"
            "event: ping\ndata: {}\n\n"
            f'event: status\ndata: {{"serial": "s1", "cultivo_id": 1, "status": "online", "n": {conexoes}}}\n\n'
        )
        return httpx.Response(200, text=corpo, headers={"content-type": "text/event-stream"})

    recebidos: list[EventoSse] = []
    reconexoes = 0

    async def ao_evento(e: EventoSse) -> None:
        recebidos.append(e)

    async def ao_reconectar() -> None:
        nonlocal reconexoes
        reconexoes += 1

    tarefa = asyncio.create_task(
        sse.ouvir_para_sempre(
            "http://p/api/stream",
            {"Authorization": "Bearer t"},
            ao_evento,
            ao_reconectar,
            transporte=httpx.MockTransport(responder),
        )
    )
    while len(recebidos) < 3:
        await asyncio.sleep(0.01)
    tarefa.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarefa
    assert all(e.tipo == "status" for e in recebidos)  # ping não chega ao callback
    assert [e.dados["n"] for e in recebidos[:3]] == [1, 2, 3]
    assert reconexoes >= 2  # não conta a primeira conexão


async def test_evento_com_erro_nao_derruba(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sse, "ESPERA_INICIAL_S", 0.01)
    corpo = 'event: a\ndata: {"i": 1}\n\nevent: a\ndata: {"i": 2}\n\n'
    transporte = httpx.MockTransport(lambda r: httpx.Response(200, text=corpo))
    vistos: list[int] = []

    async def ao_evento(e: EventoSse) -> None:
        vistos.append(e.dados["i"])
        if e.dados["i"] == 1:
            raise RuntimeError("falhou")

    tarefa = asyncio.create_task(
        sse.ouvir_para_sempre("http://p", {}, ao_evento, transporte=transporte)
    )
    while len(vistos) < 2:
        await asyncio.sleep(0.01)
    tarefa.cancel()
    assert vistos[:2] == [1, 2]


async def test_token_recusado_espera_mais(monkeypatch: pytest.MonkeyPatch) -> None:
    esperas: list[float] = []

    async def dormir(s: float) -> None:
        esperas.append(s)
        raise asyncio.CancelledError

    monkeypatch.setattr(sse.asyncio, "sleep", dormir)
    transporte = httpx.MockTransport(lambda r: httpx.Response(401, json={"erro": "token_invalido"}))

    async def nada(e: EventoSse) -> None: ...

    with pytest.raises(asyncio.CancelledError):
        await sse.ouvir_para_sempre("http://p", {}, nada, transporte=transporte)
    assert esperas == [sse.ESPERA_MAXIMA_S]
