"""Quem pode usar o bot e o que cada conversa escolheu (cultivo, alertas).

- `AcessoPlataforma` (Telegram): tudo fica na plataforma. O produtor conecta a conversa
  pelo QR code do painel (Conta → Telegram) e o bot age em nome dele com `X-Conversa`.
- `AcessoLocal` (modo terminal e testes): uma lista fixa de conversas e um arquivo local,
  todas agindo como o dono do token.

O núcleo (`servico.py`) só conhece a interface `Acesso`; trocar de canal não muda nada lá.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agroedge_bot.nucleo.api import ClienteAgroEdge, ErroApi
from agroedge_bot.nucleo.estado import Estado


@dataclass
class Conversa:
    id: str
    usuario_id: int | None  # None no acesso local (vale para qualquer evento)
    usuario_nome: str | None
    alertas: bool
    cultivo_id: int | None


class Acesso(Protocol):
    def api(self, conversa: str) -> ClienteAgroEdge:
        """Cliente da API agindo como o dono da conversa."""
        ...

    async def conversa(self, conversa: str) -> Conversa | None:
        """None: a conversa não está conectada (o bot só explica como conectar)."""
        ...

    async def todas(self) -> list[Conversa]: ...
    async def vincular(self, conversa: str, codigo: str, nome: str | None) -> Conversa: ...
    async def desvincular(self, conversa: str) -> None: ...
    async def escolher_cultivo(self, conversa: str, cultivo_id: int | None) -> None: ...
    async def definir_alertas(self, conversa: str, ligado: bool) -> None: ...


def _de_api(dados: dict[str, Any]) -> Conversa:
    return Conversa(
        id=str(dados["conversa_id"]),
        usuario_id=dados["usuario_id"],
        usuario_nome=dados.get("usuario_nome"),
        alertas=bool(dados["alertas"]),
        cultivo_id=dados.get("cultivo_id"),
    )


class AcessoPlataforma:
    """Vínculos guardados na plataforma (tabela vinculos_canal)."""

    def __init__(self, api: ClienteAgroEdge, canal: str = "telegram") -> None:
        self._api = api
        self.canal = canal

    def api(self, conversa: str) -> ClienteAgroEdge:
        return self._api.como(f"{self.canal}:{conversa}")

    async def conversa(self, conversa: str) -> Conversa | None:
        try:
            return _de_api(await self.api(conversa).conversa_atual())
        except ErroApi as erro:
            if erro.codigo == "conversa_nao_vinculada":
                return None
            raise

    async def todas(self) -> list[Conversa]:
        return [_de_api(c) for c in await self._api.conversas(self.canal)]

    async def vincular(self, conversa: str, codigo: str, nome: str | None) -> Conversa:
        return _de_api(await self._api.vincular(self.canal, codigo, conversa, nome))

    async def desvincular(self, conversa: str) -> None:
        await self.api(conversa).desconectar_conversa()

    async def escolher_cultivo(self, conversa: str, cultivo_id: int | None) -> None:
        await self.api(conversa).editar_conversa(cultivo_id=cultivo_id or 0)

    async def definir_alertas(self, conversa: str, ligado: bool) -> None:
        await self.api(conversa).editar_conversa(alertas=ligado)


class AcessoLocal:
    """Lista fixa de conversas; preferências no estado local; todas agem como o dono do
    token. Usado no modo terminal (`--console`) e nos testes."""

    def __init__(self, api: ClienteAgroEdge, permitidas: set[str], estado: Estado) -> None:
        self._api = api
        self.permitidas = permitidas
        self.estado = estado

    def api(self, conversa: str) -> ClienteAgroEdge:
        return self._api

    async def conversa(self, conversa: str) -> Conversa | None:
        if conversa not in self.permitidas:
            return None
        pref = self.estado.conversa(conversa)
        return Conversa(conversa, None, None, pref.alertas, pref.cultivo_id)

    async def todas(self) -> list[Conversa]:
        return [c for p in sorted(self.permitidas) if (c := await self.conversa(p))]

    async def vincular(self, conversa: str, codigo: str, nome: str | None) -> Conversa:
        raise ErroApi(0, "sem_vinculo", "Este modo não usa QR code: a conversa já é permitida.")

    async def desvincular(self, conversa: str) -> None:
        raise ErroApi(0, "sem_vinculo", "Este modo não desconecta conversas.")

    async def escolher_cultivo(self, conversa: str, cultivo_id: int | None) -> None:
        self.estado.conversa(conversa).cultivo_id = cultivo_id
        self.estado.salvar()

    async def definir_alertas(self, conversa: str, ligado: bool) -> None:
        self.estado.conversa(conversa).alertas = ligado
        self.estado.salvar()
