"""Engine e sessão assíncrona. Trocar SQLite por PostgreSQL é só mudar a DATABASE_URL."""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import obter_settings


def _preparar_pasta_sqlite(url: str) -> None:
    """Cria a pasta do arquivo SQLite, se for o caso."""
    prefixo = "sqlite+aiosqlite:///"
    if url.startswith(prefixo) and ":memory:" not in url:
        Path(url.removeprefix(prefixo)).parent.mkdir(parents=True, exist_ok=True)


def criar_engine(url: str, chaves_estrangeiras: bool = True) -> AsyncEngine:
    """`chaves_estrangeiras=False` só nas migrações do Alembic (ver alembic/env.py)."""
    _preparar_pasta_sqlite(url)
    engine = create_async_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _pragmas(conexao, _registro):  # type: ignore[no-untyped-def]
            cursor = conexao.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA foreign_keys={'ON' if chaves_estrangeiras else 'OFF'}")
            cursor.close()

    return engine


engine = criar_engine(obter_settings().database_url)
fabrica_sessao = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def obter_sessao() -> AsyncIterator[AsyncSession]:
    """Dependência do FastAPI."""
    async with fabrica_sessao() as sessao:
        yield sessao
