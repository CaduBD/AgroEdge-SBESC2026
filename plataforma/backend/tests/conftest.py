import os

# Antes de importar o app: banco em memória e sem MQTT.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["MQTT_HABILITADO"] = "false"
os.environ["SESSION_SECRET"] = "segredo-de-teste"

from collections.abc import AsyncIterator  # noqa: E402
from datetime import date, datetime  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.models import Cultivo, Dispositivo, Fazenda, Usuario  # noqa: E402

# Momento fixo dos testes de ingestão: 10/11/2026 12:00 UTC
AGORA = datetime(2026, 11, 10, 12, 0, 0)


class PublicadorFalso:
    """Registra o que seria publicado no broker."""

    def __init__(self) -> None:
        self.configs: list[tuple[str, dict[str, Any]]] = []
        self.comandos: list[tuple[str, dict[str, Any]]] = []
        self.fora = False

    async def config(self, serial: str, config: dict[str, Any]) -> None:
        if self.fora:
            from app.mqtt.publicador import SemBroker

            raise SemBroker()
        self.configs.append((serial, config))

    async def comando(self, serial: str, comando: dict[str, Any]) -> None:
        if self.fora:
            from app.mqtt.publicador import SemBroker

            raise SemBroker()
        self.comandos.append((serial, comando))


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    motor = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with motor.begin() as con:
        await con.exec_driver_sql("PRAGMA foreign_keys=ON")
        await con.run_sync(SQLModel.metadata.create_all)
    yield motor
    await motor.dispose()


@pytest.fixture
def fabrica(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def sessao(fabrica) -> AsyncIterator[AsyncSession]:
    async with fabrica() as s:
        yield s


@pytest.fixture
async def base(sessao: AsyncSession) -> dict:
    """Usuário, fazenda, dois cultivos e a placa agroedge-00001 (sem instalação)."""
    usuario = Usuario(nome="Equipe", email="equipe@teste", senha_hash="x")
    sessao.add(usuario)
    await sessao.flush()
    fazenda = Fazenda(usuario_id=usuario.id, nome="Fazenda")
    sessao.add(fazenda)
    await sessao.flush()
    uva = Cultivo(
        fazenda_id=fazenda.id,
        nome="Bancada",
        cultura="uva_italia",
        data_referencia=date(2026, 10, 1),
        area_m2=4,
        vazao_l_h=8,
    )
    manga = Cultivo(
        fazenda_id=fazenda.id,
        nome="Pomar",
        cultura="manga_tommy_atkins",
        data_referencia=date(2026, 9, 29),
        area_m2=40,
        vazao_l_h=64,
    )
    disp = Dispositivo(serial="agroedge-00001", usuario_id=usuario.id)
    sessao.add_all([uva, manga, disp])
    await sessao.commit()
    return {"usuario": usuario, "fazenda": fazenda, "uva": uva, "manga": manga, "disp": disp}
