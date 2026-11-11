"""Ambiente do Alembic com engine assíncrona. A URL vem da DATABASE_URL."""

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registra as tabelas no metadata)
from alembic import context
from app.config import obter_settings
from app.db import criar_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _configurar(conexao: Connection) -> None:
    context.configure(
        connection=conexao,
        target_metadata=target_metadata,
        render_as_batch=conexao.dialect.name == "sqlite",  # ALTER TABLE no SQLite
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _rodar_online() -> None:
    # No SQLite o batch recria tabelas (cópia → DROP → RENAME); com chaves estrangeiras
    # ligadas, o DROP de uma tabela referenciada falha. Desligadas só durante a migração.
    engine = criar_engine(obter_settings().database_url, chaves_estrangeiras=False)
    async with engine.connect() as conexao:
        await conexao.run_sync(_configurar)
    await engine.dispose()


def rodar_offline() -> None:
    context.configure(
        url=obter_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    rodar_offline()
else:
    asyncio.run(_rodar_online())
