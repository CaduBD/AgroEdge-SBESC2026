"""Fuso de exibição e conversões. O banco guarda tudo em UTC; o fuso local só aparece aqui."""

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.config import obter_settings
from app.erros import ErroApp
from app.models import datetime_para_ts


@lru_cache
def fuso() -> ZoneInfo:
    return ZoneInfo(obter_settings().tz_exibicao)


def hoje_local(agora: datetime) -> date:
    """Data local de um instante UTC sem fuso."""
    return agora.replace(tzinfo=UTC).astimezone(fuso()).date()


def data_local_do_ts(ts: int) -> date:
    return datetime.fromtimestamp(ts, fuso()).date()


def inicio_do_dia_local(dia: date) -> int:
    """Unix do início (00:00 local) de um dia."""
    return int(datetime.combine(dia, time(0, 0), fuso()).timestamp())


def proxima_ocorrencia(hora: time, agora: datetime) -> datetime:
    """Próxima vez em que o relógio local marca `hora`, devolvida em UTC sem fuso."""
    local = agora.replace(tzinfo=UTC).astimezone(fuso())
    candidato = datetime.combine(local.date(), hora, fuso())
    if candidato <= local:
        candidato += timedelta(days=1)
    return candidato.astimezone(UTC).replace(tzinfo=None)


def ler_instante(texto: str, fim_do_dia: bool = False) -> int:
    """`AAAA-MM-DD` (dia local) ou data e hora ISO 8601 → Unix.

    Para uma data pura usada como fim de período, devolve o início do dia seguinte
    (fim exclusivo), para que `ate=2026-11-10` inclua o dia 10 inteiro.
    """
    try:
        if len(texto) == 10:
            dia = date.fromisoformat(texto)
            return inicio_do_dia_local(dia + timedelta(days=1 if fim_do_dia else 0))
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as erro:
        raise ErroApp(400, "data_invalida", f"Data inválida: {texto}") from erro
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return int(momento.timestamp())


def periodo(de: str | None, ate: str | None, agora: datetime, padrao_dias: int) -> tuple[int, int]:
    """Período [inicio, fim) em Unix. Padrão: os últimos `padrao_dias` dias até agora."""
    fim = ler_instante(ate, fim_do_dia=True) if ate else datetime_para_ts(agora)
    inicio = ler_instante(de) if de else fim - padrao_dias * 86400
    if inicio >= fim:
        raise ErroApp(400, "periodo_invalido", "O início do período precisa ser antes do fim.")
    return inicio, fim
