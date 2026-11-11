"""Cultivo: detalhe, edição (regra 9.4), nova poda, arquivar e os dados para as telas."""

import csv
import io
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.auth import CultivoDoUsuario, Sessao
from app.erros import ErroApp
from app.models import agora_utc
from app.rotas.comum import PublicadorDep, cultivo_saida
from app.schemas.api import (
    CultivoEdicao,
    CultivoResumo,
    CultivoSaida,
    DiarioSaida,
    IrrigacaoSaida,
    PodaEntrada,
    ResumoSaida,
    SerieSaida,
)
from app.servicos import consultas
from app.servicos.configuracao import (
    instalacao_ativa_do_cultivo,
    normalizar_solo,
    reconfigurar,
    validar_cultivo,
)
from app.tempo import fuso, periodo

rotas = APIRouter(prefix="/api/cultivos", tags=["cultivos"])

CAMPOS_SO_DA_PLATAFORMA = {"nome"}  # mudar só estes não gera nova versão de config


@rotas.get("/{cultivo_id}", response_model=CultivoSaida)
async def detalhe(cultivo: CultivoDoUsuario, sessao: Sessao) -> CultivoSaida:
    return await cultivo_saida(sessao, cultivo, agora_utc())


@rotas.patch("/{cultivo_id}", response_model=CultivoSaida)
async def editar(
    entrada: CultivoEdicao, cultivo: CultivoDoUsuario, sessao: Sessao, publicador: PublicadorDep
) -> CultivoSaida:
    """Salva. Se houver placa instalada, publica a nova config (`configuracao.aplicada`
    fica falsa até a placa confirmar)."""
    dados = entrada.model_dump(exclude_unset=True)
    obrigatorios = {"nome", "cultura", "data_referencia", "textura_solo", "eficiencia",
                    "area_m2", "vazao_l_h", "fonte_irrigacao", "inicio_uso",
                    "irrigacao_automatica", "hora_irrigacao"}  # fmt: skip
    nulos = [c for c in obrigatorios if c in dados and dados[c] is None]
    if nulos:
        raise ErroApp(400, "campo_obrigatorio", f"Campos não podem ficar vazios: {sorted(nulos)}")
    if dados.get("textura_solo") == "avancado" and "agua_disp" not in dados:
        dados["agua_disp"] = cultivo.agua_disp
    if dados.get("agua_disp") is None:
        dados.pop("agua_disp", None)

    antes = cultivo.model_dump()
    for campo, valor in dados.items():
        setattr(cultivo, campo, valor)
    normalizar_solo(cultivo)
    validar_cultivo(cultivo)
    mudou = {c for c, v in cultivo.model_dump().items() if antes.get(c) != v}
    if mudou:
        cultivo.atualizado_em = agora_utc()
    if mudou - CAMPOS_SO_DA_PLATAFORMA:
        await reconfigurar(sessao, publicador, cultivo)
    sessao.add(cultivo)
    await sessao.commit()
    return await cultivo_saida(sessao, cultivo, agora_utc())


@rotas.post("/{cultivo_id}/poda", response_model=CultivoSaida)
async def nova_poda(
    entrada: PodaEntrada, cultivo: CultivoDoUsuario, sessao: Sessao, publicador: PublicadorDep
) -> CultivoSaida:
    """Registra nova poda (uva) ou floração (manga): nova data de referência e nova config."""
    cultivo.data_referencia = entrada.data
    cultivo.atualizado_em = agora_utc()
    await reconfigurar(sessao, publicador, cultivo)
    sessao.add(cultivo)
    await sessao.commit()
    return await cultivo_saida(sessao, cultivo, agora_utc())


@rotas.post("/{cultivo_id}/arquivar", response_model=CultivoSaida)
async def arquivar(cultivo: CultivoDoUsuario, sessao: Sessao) -> CultivoSaida:
    if await instalacao_ativa_do_cultivo(sessao, cultivo.id):  # type: ignore[arg-type]
        raise ErroApp(
            409,
            "cultivo_com_placa",
            "Este cultivo tem uma placa instalada. Instale a placa em outro cultivo antes.",
        )
    cultivo.arquivado = True
    cultivo.atualizado_em = agora_utc()
    sessao.add(cultivo)
    await sessao.commit()
    return await cultivo_saida(sessao, cultivo, agora_utc())


# ---------------------------------------------------------------- dados


@rotas.get("/{cultivo_id}/resumo", response_model=ResumoSaida, tags=["dados"])
async def resumo(cultivo: CultivoDoUsuario, sessao: Sessao) -> dict[str, Any]:
    """Tudo o que a tela Início mostra, num só objeto (é o "/hoje" do chatbot)."""
    agora = agora_utc()
    dados = await consultas.resumo(sessao, cultivo, agora)
    base = (await cultivo_saida(sessao, cultivo, agora)).model_dump()
    dados["cultivo"] = CultivoResumo.model_validate({**base, **dados["cultivo"]})
    return dados


@rotas.get("/{cultivo_id}/leituras", response_model=SerieSaida, tags=["dados"])
async def leituras(
    cultivo: CultivoDoUsuario,
    sessao: Sessao,
    de: str | None = Query(None, description="AAAA-MM-DD (dia local) ou ISO 8601; padrão: 7 dias"),
    ate: str | None = Query(
        None, description="AAAA-MM-DD (inclui o dia) ou ISO 8601; padrão: agora"
    ),
    variaveis: str = Query("temp_c,ur_pct,vento_ms,rad_wm2,chuva_mm", examples=["temp_c,chuva_mm"]),
    resolucao: Literal["bruta", "hora", "dia"] | None = Query(
        None, description="Padrão: bruta até 31 dias, hora até 180, dia acima disso"
    ),
) -> dict[str, Any]:
    inicio, fim = periodo(de, ate, agora_utc(), padrao_dias=7)
    lista = [v.strip() for v in variaveis.split(",") if v.strip()]
    return await consultas.serie_leituras(sessao, cultivo.id, inicio, fim, lista, resolucao)  # type: ignore[arg-type]


@rotas.get("/{cultivo_id}/diarios", response_model=list[DiarioSaida], tags=["dados"])
async def diarios(
    cultivo: CultivoDoUsuario,
    sessao: Sessao,
    de: str | None = Query(None, description="padrão: 30 dias"),
    ate: str | None = None,
) -> list[Any]:
    inicio, fim = periodo(de, ate, agora_utc(), padrao_dias=30)
    return await consultas.diarios(sessao, cultivo.id, inicio, fim)  # type: ignore[arg-type]


@rotas.get("/{cultivo_id}/irrigacoes", response_model=list[IrrigacaoSaida], tags=["dados"])
async def irrigacoes(
    cultivo: CultivoDoUsuario,
    sessao: Sessao,
    de: str | None = Query(None, description="padrão: 30 dias"),
    ate: str | None = None,
) -> list[Any]:
    inicio, fim = periodo(de, ate, agora_utc(), padrao_dias=30)
    return await consultas.irrigacoes(sessao, cultivo.id, inicio, fim)  # type: ignore[arg-type]


# ---------------------------------------------------------------- CSV


def _celula(valor: Any) -> str:
    """Formato que o Excel em pt-BR entende: vírgula decimal, data local."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, float):
        return f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(valor, list):
        return " | ".join(str(v) for v in valor)
    return str(valor)


def _hora_local(ts: int | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, UTC).astimezone(fuso()).strftime("%d/%m/%Y %H:%M")


def _csv(cabecalho: list[str], linhas: Iterable[list[Any]]) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow([_celula(v) for v in linha])
    return saida.getvalue()


# (campo, cabeçalho para o Excel). Rótulos e unidades em português (apêndice C).
COLUNAS_DIARIO = [
    ("dap", "Dias após a referência"), ("fase", "Fase"), ("kc", "Kc"),
    ("tmax", "Temp. máx. (°C)"), ("tmin", "Temp. mín. (°C)"), ("ur", "Umidade (%)"),
    ("u2", "Vento (m/s)"), ("rs", "Radiação (MJ/m²)"), ("chuva", "Chuva (mm)"),
    ("irrigacao", "Irrigação (mm)"), ("et0", "ET0 (mm)"), ("etc", "ETc (mm)"),
    ("taw", "TAW (mm)"), ("deficit", "Déficit (mm)"), ("classe", "Estado hídrico"),
    ("lamina_bruta", "Lâmina (mm)"), ("minutos", "Minutos de válvula"),
    ("consumo_l_planta", "Consumo (L/planta)"), ("aplicar_l_planta", "Aplicar (L/planta)"),
    ("avisos", "Avisos"),
]  # fmt: skip
COLUNAS_LEITURA = [
    ("temp_c", "Temperatura (°C)"), ("ur_pct", "Umidade (%)"), ("vento_ms", "Vento (m/s)"),
    ("rad_wm2", "Radiação (W/m²)"), ("chuva_mm", "Chuva (mm)"), ("bat_v", "Bateria (V)"),
    ("rssi", "Sinal (dBm)"), ("buf", "No buffer"),
]  # fmt: skip
COLUNAS_IRRIGACAO = [
    ("minutos", "Minutos"), ("mm", "Lâmina (mm)"), ("origem", "Origem"), ("estado", "Estado"),
]  # fmt: skip
ROTULOS: dict[str, dict[Any, str]] = {
    "classe": {0: "Adequado", 1: "Déficit moderado", 2: "Déficit crítico"},
    "origem": {"automatica": "Automática", "manual": "Manual"},
    "estado": {"iniciada": "Em andamento", "concluida": "Concluída", "cancelada": "Cancelada",
               "interrompida": "Interrompida"},
}  # fmt: skip


def _valores(obj: Any, colunas: list[tuple[str, str]]) -> list[Any]:
    saida = []
    for campo, _ in colunas:
        valor = getattr(obj, campo)
        chave = valor.value if hasattr(valor, "value") else valor
        if campo in ROTULOS and chave is not None:
            valor = ROTULOS[campo].get(chave, valor)
        saida.append(valor)
    return saida


def _cabecalho(colunas: list[tuple[str, str]]) -> list[str]:
    return [rotulo for _, rotulo in colunas]


@rotas.get(
    "/{cultivo_id}/exportar.csv",
    tags=["dados"],
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV (;) para o Excel"}},
)
async def exportar_csv(
    cultivo: CultivoDoUsuario,
    sessao: Sessao,
    tipo: Literal["leituras", "diarios", "irrigacoes"] = "diarios",
    de: str | None = Query(None, description="padrão: 30 dias"),
    ate: str | None = None,
) -> Response:
    inicio, fim = periodo(de, ate, agora_utc(), padrao_dias=30)
    cid: int = cultivo.id  # type: ignore[assignment]
    if tipo == "leituras":
        dados_l = await consultas.leituras_brutas(sessao, cid, inicio, fim)
        texto = _csv(
            ["Data e hora", *_cabecalho(COLUNAS_LEITURA)],
            ([_hora_local(lt.ts), *_valores(lt, COLUNAS_LEITURA)] for lt in dados_l),
        )
    elif tipo == "diarios":
        dados_d = await consultas.diarios(sessao, cid, inicio, fim)
        texto = _csv(
            ["Data", *_cabecalho(COLUNAS_DIARIO)],
            ([d.data.strftime("%d/%m/%Y"), *_valores(d, COLUNAS_DIARIO)] for d in dados_d),
        )
    else:
        dados_i = await consultas.irrigacoes(sessao, cid, inicio, fim)
        texto = _csv(
            ["Início", "Fim", *_cabecalho(COLUNAS_IRRIGACAO)],
            (
                [_hora_local(i.ts_inicio), _hora_local(i.ts_fim), *_valores(i, COLUNAS_IRRIGACAO)]
                for i in dados_i
            ),
        )
    nome = f"agroedge_{tipo}_cultivo{cid}.csv"
    return Response(
        content="﻿" + texto,  # BOM: o Excel reconhece UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
