"""INSERT ignorando conflito e UPSERT, funcionando em SQLite e PostgreSQL."""

from typing import Any

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel


def _insert(sessao: AsyncSession, modelo: type[SQLModel]):  # type: ignore[no-untyped-def]
    dialeto = sessao.bind.dialect.name if sessao.bind else "sqlite"
    tabela = modelo.__table__  # type: ignore[attr-defined]
    return postgresql.insert(tabela) if dialeto == "postgresql" else sqlite.insert(tabela)


async def inserir_ignorando(
    sessao: AsyncSession, modelo: type[SQLModel], valores: dict[str, Any], chaves: list[str]
) -> bool:
    """Insere; se a chave única já existir, não faz nada. Devolve True se inseriu."""
    stmt = _insert(sessao, modelo).values(**valores).on_conflict_do_nothing(index_elements=chaves)
    resultado = await sessao.execute(stmt)
    return bool(resultado.rowcount)  # type: ignore[attr-defined]


async def upsert(
    sessao: AsyncSession, modelo: type[SQLModel], valores: dict[str, Any], chaves: list[str]
) -> None:
    """Insere ou, se a chave única já existir, atualiza os demais campos."""
    stmt = _insert(sessao, modelo).values(**valores)
    atualizar = {k: stmt.excluded[k] for k in valores if k not in chaves and k != "id"}
    await sessao.execute(stmt.on_conflict_do_update(index_elements=chaves, set_=atualizar))
