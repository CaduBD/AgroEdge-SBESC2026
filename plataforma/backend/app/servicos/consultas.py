"""Consultas de leitura da API: resumo da tela Início, séries, diários, irrigações.

Os dados de um cultivo são os registros cujas instalações pertencem a ele (regra 9.2).
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.catalogo import cultura as cultura_do_catalogo
from app.erros import ErroApp
from app.models import (
    Cultivo,
    Diario,
    Dispositivo,
    EstadoIrrigacao,
    Fazenda,
    Instalacao,
    Irrigacao,
    Leitura,
    datetime_para_ts,
    ts_para_datetime,
)
from app.servicos.configuracao import instalacao_ativa_do_cultivo, raiz_efetiva, taw_raw
from app.servicos.status import status_dispositivo
from app.tempo import data_local_do_ts, fuso, hoje_local, inicio_do_dia_local, proxima_ocorrencia

VARIAVEIS = ("temp_c", "ur_pct", "vento_ms", "rad_wm2", "chuva_mm", "bat_v", "rssi")
SOMADAS = {"chuva_mm"}  # nas resoluções agregadas, chuva soma; o resto é média
LIMITE_BRUTA_DIAS = 31
LIMITE_HORA_DIAS = 180
IRRIGACAO_ABERTA_MAX = timedelta(hours=24)  # "iniciada" mais antiga que isso não conta como aberta


def _do_cultivo(cultivo_id: int):  # type: ignore[no-untyped-def]
    """Subconsulta com as instalações do cultivo."""
    return select(Instalacao.id).where(col(Instalacao.cultivo_id) == cultivo_id)


# ---------------------------------------------------------------- ciclo


def ciclo_do_cultivo(cultivo: Cultivo, agora: datetime, fase_placa: str | None) -> dict[str, Any]:
    dados = cultura_do_catalogo(cultivo.cultura) or {}
    ciclo_dias = int(dados.get("ciclo_dias", 0))
    dias = (hoje_local(agora) - cultivo.data_referencia).days
    fases = dados.get("fases") or []
    fase = fase_placa
    if fase is None and fases and dias >= 0:
        acumulado = 0
        for item in fases:
            acumulado += item["dias"]
            if dias < acumulado:
                fase = item["chave"]
                break
    nome = next((f["nome"] for f in fases if f["chave"] == fase), None)
    return {
        "dias": dias,
        "ciclo_dias": ciclo_dias,
        "fora_do_ciclo": dias < 0 or dias > ciclo_dias,
        "fase": fase,
        "fase_nome": nome,
    }


# ---------------------------------------------------------------- resumo (tela Início)


async def resumo(sessao: AsyncSession, cultivo: Cultivo, agora: datetime) -> dict[str, Any]:
    cultivo_id: int = cultivo.id  # type: ignore[assignment]
    fazenda = await sessao.get(Fazenda, cultivo.fazenda_id)
    taw, raw = taw_raw(cultivo)

    instalacao = await instalacao_ativa_do_cultivo(sessao, cultivo_id)
    dispositivo = await sessao.get(Dispositivo, instalacao.dispositivo_id) if instalacao else None

    ultima_leitura = (
        await sessao.execute(
            select(Leitura)
            .where(col(Leitura.instalacao_id).in_(_do_cultivo(cultivo_id)))
            .order_by(col(Leitura.ts).desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ultimo_diario = (
        await sessao.execute(
            select(Diario)
            .where(col(Diario.instalacao_id).in_(_do_cultivo(cultivo_id)))
            .order_by(col(Diario.data).desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "cultivo": {
            **cultivo.model_dump(),
            "fazenda": fazenda.model_dump() if fazenda else None,
            "cultura_info": cultura_do_catalogo(cultivo.cultura),
            "raiz_efetiva_m": raiz_efetiva(cultivo),
            "taw_mm": taw,
            "raw_mm": raw,
        },
        "dispositivo": await _dispositivo_resumo(sessao, dispositivo, instalacao, agora),
        "ultima_leitura": ultima_leitura.model_dump() if ultima_leitura else None,
        "ultimo_diario": ultimo_diario.model_dump() if ultimo_diario else None,
        "ciclo": ciclo_do_cultivo(cultivo, agora, ultimo_diario.fase if ultimo_diario else None),
        "valvula": await _valvula(sessao, cultivo, ultimo_diario, agora),
        "ultimos_7_dias": await _ultimos_dias(sessao, cultivo_id, agora, 7),
    }


async def ultima_leitura_do_dispositivo(
    sessao: AsyncSession, dispositivo_id: int
) -> Leitura | None:
    return (
        await sessao.execute(
            select(Leitura)
            .where(col(Leitura.dispositivo_id) == dispositivo_id)
            .order_by(col(Leitura.ts).desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _dispositivo_resumo(
    sessao: AsyncSession,
    disp: Dispositivo | None,
    instalacao: Instalacao | None,
    agora: datetime,
) -> dict[str, Any] | None:
    if disp is None or instalacao is None:
        return None
    ultima = await ultima_leitura_do_dispositivo(sessao, disp.id)  # type: ignore[arg-type]
    status = status_dispositivo(disp, ultima, agora)
    return {
        "serial": disp.serial,
        "apelido": disp.apelido,
        "status": status.estado,
        "sincronizando": status.sincronizando,
        "ultima_telemetria": status.ultima_telemetria,
        "ultimo_contato": disp.ultimo_contato,
        "bat_v": ultima.bat_v if ultima else None,
        "rssi": ultima.rssi if ultima else None,
        "instalacao_id": instalacao.id,
        "cfg_v": instalacao.cfg_v,
        "cfg_v_aplicada": instalacao.cfg_v_aplicada,
        "cfg_aplicada": instalacao.cfg_v_aplicada == instalacao.cfg_v,
    }


async def _valvula(
    sessao: AsyncSession, cultivo: Cultivo, ultimo_diario: Diario | None, agora: datetime
) -> dict[str, Any]:
    cultivo_id: int = cultivo.id  # type: ignore[assignment]
    recentes = (
        (
            await sessao.execute(
                select(Irrigacao)
                .where(col(Irrigacao.instalacao_id).in_(_do_cultivo(cultivo_id)))
                .order_by(col(Irrigacao.ts_inicio).desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    limite = datetime_para_ts(agora - IRRIGACAO_ABERTA_MAX)
    em_andamento = next(
        (i for i in recentes if i.estado == EstadoIrrigacao.iniciada and i.ts_inicio >= limite),
        None,
    )
    ultima = next((i for i in recentes if i.estado != EstadoIrrigacao.iniciada), None)
    proxima = None
    if (
        cultivo.irrigacao_automatica
        and ultimo_diario is not None
        and (ultimo_diario.minutos or 0) > 0
    ):
        proxima = proxima_ocorrencia(cultivo.hora_irrigacao, agora)
    return {
        "aberta": em_andamento is not None,
        "em_andamento": em_andamento.model_dump() if em_andamento else None,
        "ultima": ultima.model_dump() if ultima else None,
        "proxima_prevista": proxima,
    }


async def _ultimos_dias(
    sessao: AsyncSession, cultivo_id: int, agora: datetime, n: int
) -> list[dict[str, Any]]:
    """Por dia (local): chuva, irrigação, ETc, ET₀ e classe. Hoje ainda sem fechamento:
    chuva somada das leituras e irrigação somada das irrigações do dia."""
    hoje = hoje_local(agora)
    dias = [hoje - timedelta(days=i) for i in range(n - 1, -1, -1)]
    diarios = {
        d.data: d
        for d in (
            await sessao.execute(
                select(Diario).where(
                    col(Diario.instalacao_id).in_(_do_cultivo(cultivo_id)),
                    col(Diario.data) >= dias[0],
                )
            )
        ).scalars()
    }
    inicio_hoje = inicio_do_dia_local(hoje)
    chuva_hoje = (
        await sessao.execute(
            select(func.sum(Leitura.chuva_mm)).where(
                col(Leitura.instalacao_id).in_(_do_cultivo(cultivo_id)),
                col(Leitura.ts) > inicio_hoje,
            )
        )
    ).scalar_one()
    irrigacao_hoje = (
        await sessao.execute(
            select(func.sum(Irrigacao.mm)).where(
                col(Irrigacao.instalacao_id).in_(_do_cultivo(cultivo_id)),
                col(Irrigacao.ts_inicio) >= inicio_hoje,
            )
        )
    ).scalar_one()

    saida = []
    for dia in dias:
        d = diarios.get(dia)
        if d is not None:
            item = {"chuva": d.chuva, "irrigacao": d.irrigacao, "etc": d.etc, "et0": d.et0}
            item["classe"] = d.classe
        elif dia == hoje:
            item = {
                "chuva": round(chuva_hoje, 1) if chuva_hoje is not None else None,
                "irrigacao": round(irrigacao_hoje, 1) if irrigacao_hoje is not None else None,
                "etc": None,
                "et0": None,
                "classe": None,
            }
        else:
            item = {"chuva": None, "irrigacao": None, "etc": None, "et0": None, "classe": None}
        saida.append({"data": dia, "hoje": dia == hoje, "fechado": d is not None, **item})
    return saida


# ---------------------------------------------------------------- séries de leituras


def resolucao_padrao(inicio: int, fim: int) -> str:
    dias = (fim - inicio) / 86400
    if dias <= LIMITE_BRUTA_DIAS:
        return "bruta"
    return "hora" if dias <= LIMITE_HORA_DIAS else "dia"


async def intervalo_do_cultivo(sessao: AsyncSession, cultivo_id: int) -> int:
    """Intervalo de telemetria (min) das placas que passaram pelo cultivo; o maior vale."""
    valor = (
        await sessao.execute(
            select(func.max(Dispositivo.intervalo_telemetria_min))
            .join(Instalacao, col(Instalacao.dispositivo_id) == col(Dispositivo.id))
            .where(col(Instalacao.cultivo_id) == cultivo_id)
        )
    ).scalar_one()
    return int(valor or 15)


async def serie_leituras(
    sessao: AsyncSession,
    cultivo_id: int,
    inicio: int,
    fim: int,
    variaveis: list[str],
    resolucao: str | None,
) -> dict[str, Any]:
    desconhecidas = [v for v in variaveis if v not in VARIAVEIS]
    if desconhecidas:
        raise ErroApp(400, "variavel_desconhecida", f"Variáveis desconhecidas: {desconhecidas}")
    resolucao = resolucao or resolucao_padrao(inicio, fim)
    if resolucao == "bruta" and fim - inicio > LIMITE_BRUTA_DIAS * 86400:
        raise ErroApp(
            400,
            "periodo_longo",
            f"Resolução bruta vai até {LIMITE_BRUTA_DIAS} dias; use 'hora' ou 'dia'.",
        )

    filtro = (
        col(Leitura.instalacao_id).in_(_do_cultivo(cultivo_id)),
        col(Leitura.ts) >= inicio,
        col(Leitura.ts) < fim,
    )
    if resolucao == "bruta":
        linhas = (
            await sessao.execute(
                select(Leitura.ts, *[getattr(Leitura, v) for v in variaveis])
                .where(*filtro)
                .order_by(col(Leitura.ts))
            )
        ).all()
    else:
        tamanho = 3600 if resolucao == "hora" else 86400
        # Baldes alinhados ao relógio local (o dia começa à meia-noite de Petrolina).
        deslocamento = int(fuso().utcoffset(datetime.now()).total_seconds())  # type: ignore[union-attr]
        balde = col(Leitura.ts) - ((col(Leitura.ts) + deslocamento) % tamanho)
        agregados = [
            (func.sum if v in SOMADAS else func.avg)(getattr(Leitura, v)).label(v)
            for v in variaveis
        ]
        linhas = (
            await sessao.execute(
                select(balde.label("ts"), *agregados).where(*filtro).group_by(balde).order_by(balde)
            )
        ).all()

    pontos = [
        {
            "ts": int(linha[0]),
            **{
                v: (round(valor, 2) if isinstance(valor, float) else valor)
                for v, valor in zip(variaveis, linha[1:], strict=True)
            },
        }
        for linha in linhas
    ]
    return {
        "resolucao": resolucao,
        "de": inicio,
        "ate": fim,
        "variaveis": variaveis,
        "pontos": pontos,
        "lacunas": await lacunas(sessao, cultivo_id, inicio, fim),
    }


async def lacunas(sessao: AsyncSession, cultivo_id: int, inicio: int, fim: int) -> list[dict]:
    """Regra 9.7: intervalos entre leituras consecutivas maiores que 2 × intervalo."""
    limite = 2 * 60 * await intervalo_do_cultivo(sessao, cultivo_id)
    tss = (
        (
            await sessao.execute(
                select(Leitura.ts)
                .where(
                    col(Leitura.instalacao_id).in_(_do_cultivo(cultivo_id)),
                    col(Leitura.ts) >= inicio,
                    col(Leitura.ts) < fim,
                )
                .order_by(col(Leitura.ts))
            )
        )
        .scalars()
        .all()
    )
    return [{"inicio": a, "fim": b} for a, b in zip(tss, tss[1:], strict=False) if b - a > limite]


# ---------------------------------------------------------------- diários e irrigações


async def diarios(sessao: AsyncSession, cultivo_id: int, inicio: int, fim: int) -> list[Diario]:
    de: date = data_local_do_ts(inicio)
    ate: date = data_local_do_ts(fim - 1)
    return list(
        (
            await sessao.execute(
                select(Diario)
                .where(
                    col(Diario.instalacao_id).in_(_do_cultivo(cultivo_id)),
                    col(Diario.data) >= de,
                    col(Diario.data) <= ate,
                )
                .order_by(col(Diario.data))
            )
        ).scalars()
    )


async def irrigacoes(
    sessao: AsyncSession, cultivo_id: int, inicio: int, fim: int
) -> list[Irrigacao]:
    return list(
        (
            await sessao.execute(
                select(Irrigacao)
                .where(
                    col(Irrigacao.instalacao_id).in_(_do_cultivo(cultivo_id)),
                    col(Irrigacao.ts_inicio) >= inicio,
                    col(Irrigacao.ts_inicio) < fim,
                )
                .order_by(col(Irrigacao.ts_inicio))
            )
        ).scalars()
    )


async def leituras_brutas(
    sessao: AsyncSession, cultivo_id: int, inicio: int, fim: int
) -> list[Leitura]:
    return list(
        (
            await sessao.execute(
                select(Leitura)
                .where(
                    col(Leitura.instalacao_id).in_(_do_cultivo(cultivo_id)),
                    col(Leitura.ts) >= inicio,
                    col(Leitura.ts) < fim,
                )
                .order_by(col(Leitura.ts))
            )
        ).scalars()
    )


__all__ = ["ts_para_datetime"]
