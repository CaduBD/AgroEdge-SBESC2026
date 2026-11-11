"""Catálogo de culturas, fazendas e criação/listagem de cultivos de uma fazenda."""

from typing import Any

from fastapi import APIRouter, Query, Response
from sqlalchemy import func
from sqlmodel import col, select

from app.auth import FazendaDoUsuario, Sessao, UsuarioAtual
from app.catalogo import culturas
from app.erros import ErroApp
from app.models import Cultivo, Fazenda, agora_utc
from app.rotas.comum import cultivo_saida
from app.schemas.api import (
    CultivoEntrada,
    CultivoSaida,
    Cultura,
    FazendaEdicao,
    FazendaEntrada,
    FazendaSaida,
)
from app.servicos.configuracao import normalizar_solo, validar_cultivo

rotas = APIRouter(prefix="/api", tags=["fazendas"])


@rotas.get("/culturas", response_model=list[Cultura], tags=["catálogo"])
async def listar_culturas(_usuario: UsuarioAtual) -> list[dict[str, Any]]:
    return culturas()


async def _fazenda_saida(sessao: Sessao, fazenda: Fazenda) -> FazendaSaida:
    n = (
        await sessao.execute(
            select(func.count()).select_from(Cultivo).where(col(Cultivo.fazenda_id) == fazenda.id)
        )
    ).scalar_one()
    return FazendaSaida.model_validate({**fazenda.model_dump(), "n_cultivos": n})


async def _nome_livre(
    sessao: Sessao, usuario_id: int, nome: str, exceto: int | None = None
) -> None:
    existe = (
        await sessao.execute(
            select(Fazenda.id).where(
                col(Fazenda.usuario_id) == usuario_id,
                func.lower(Fazenda.nome) == nome.strip().lower(),
                col(Fazenda.id) != (exceto or -1),
            )
        )
    ).first()
    if existe:
        raise ErroApp(409, "nome_repetido", "Já existe uma fazenda com esse nome.")


@rotas.get("/fazendas", response_model=list[FazendaSaida])
async def listar_fazendas(usuario: UsuarioAtual, sessao: Sessao) -> list[FazendaSaida]:
    fazendas = (
        await sessao.execute(
            select(Fazenda).where(col(Fazenda.usuario_id) == usuario.id).order_by(col(Fazenda.nome))
        )
    ).scalars()
    return [await _fazenda_saida(sessao, f) for f in fazendas]


@rotas.post("/fazendas", response_model=FazendaSaida, status_code=201)
async def criar_fazenda(
    entrada: FazendaEntrada, usuario: UsuarioAtual, sessao: Sessao
) -> FazendaSaida:
    await _nome_livre(sessao, usuario.id, entrada.nome)  # type: ignore[arg-type]
    fazenda = Fazenda(usuario_id=usuario.id, **entrada.model_dump())  # type: ignore[arg-type]
    fazenda.nome = fazenda.nome.strip()
    sessao.add(fazenda)
    await sessao.commit()
    return await _fazenda_saida(sessao, fazenda)


@rotas.patch("/fazendas/{fazenda_id}", response_model=FazendaSaida)
async def editar_fazenda(
    entrada: FazendaEdicao, fazenda: FazendaDoUsuario, sessao: Sessao
) -> FazendaSaida:
    dados = entrada.model_dump(exclude_unset=True)
    if "nome" in dados:
        if dados["nome"] is None:
            raise ErroApp(400, "nome_obrigatorio", "O nome da fazenda é obrigatório.")
        await _nome_livre(sessao, fazenda.usuario_id, dados["nome"], exceto=fazenda.id)
        dados["nome"] = dados["nome"].strip()
    for campo, valor in dados.items():
        setattr(fazenda, campo, valor)
    sessao.add(fazenda)
    await sessao.commit()
    return await _fazenda_saida(sessao, fazenda)


@rotas.delete("/fazendas/{fazenda_id}", status_code=204)
async def excluir_fazenda(fazenda: FazendaDoUsuario, sessao: Sessao) -> Response:
    if (await _fazenda_saida(sessao, fazenda)).n_cultivos:
        raise ErroApp(
            409, "fazenda_com_cultivos", "Só é possível excluir uma fazenda sem cultivos."
        )
    await sessao.delete(fazenda)
    await sessao.commit()
    return Response(status_code=204)


@rotas.get("/fazendas/{fazenda_id}/cultivos", response_model=list[CultivoSaida])
async def listar_cultivos(
    fazenda: FazendaDoUsuario,
    sessao: Sessao,
    arquivados: bool = Query(False, description="Incluir cultivos arquivados"),
) -> list[CultivoSaida]:
    consulta = select(Cultivo).where(col(Cultivo.fazenda_id) == fazenda.id)
    if not arquivados:
        consulta = consulta.where(col(Cultivo.arquivado).is_(False))
    agora = agora_utc()
    cultivos = (await sessao.execute(consulta.order_by(col(Cultivo.nome)))).scalars().all()
    return [await cultivo_saida(sessao, c, agora) for c in cultivos]


@rotas.post("/fazendas/{fazenda_id}/cultivos", response_model=CultivoSaida, status_code=201)
async def criar_cultivo(
    entrada: CultivoEntrada, fazenda: FazendaDoUsuario, sessao: Sessao
) -> CultivoSaida:
    dados = entrada.model_dump()
    if dados["agua_disp"] is None:
        dados["agua_disp"] = 0.11  # substituído pelo preset, exceto em "avancado"
    cultivo = Cultivo(fazenda_id=fazenda.id, **dados)  # type: ignore[arg-type]
    if cultivo.textura_solo == "avancado" and entrada.agua_disp is None:
        raise ErroApp(400, "agua_disp_obrigatoria", "Informe a água disponível do solo.")
    normalizar_solo(cultivo)
    validar_cultivo(cultivo)
    sessao.add(cultivo)
    await sessao.commit()
    return await cultivo_saida(sessao, cultivo, agora_utc())
