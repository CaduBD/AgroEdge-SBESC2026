"""Cliente da API REST da plataforma (CHATBOT.md, seções 3 e 4).

Só leitura e comandos da válvula. Devolve os dicionários da API como vieram: quem
formata é `textos.py`. Erros viram `ErroApi`, com a `mensagem` pronta para o usuário.
"""

from __future__ import annotations

import copy
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(15, connect=5)


class ErroApi(Exception):
    """Erro da plataforma (`{"erro": ..., "mensagem": ...}`) ou falha de conexão."""

    def __init__(self, status: int, codigo: str, mensagem: str) -> None:
        super().__init__(f"{status} {codigo}: {mensagem}")
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


SEM_CONEXAO = (
    "Não consegui falar com a plataforma AgroEdge agora. "
    "Confira se ela está ligada e tente de novo em instantes."
)


class ClienteAgroEdge:
    def __init__(
        self, url: str, token: str, transporte: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.conversa: str | None = None
        self._http = httpx.AsyncClient(
            base_url=self.url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=TIMEOUT,
            transport=transporte,
        )

    @property
    def cabecalhos(self) -> dict[str, str]:
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        if self.conversa:
            cabecalhos["X-Conversa"] = self.conversa
        return cabecalhos

    def como(self, conversa: str) -> ClienteAgroEdge:
        """O mesmo cliente agindo em nome de uma conversa vinculada (`telegram:<chat id>`):
        a plataforma responde como o usuário dono dela. Compartilha a conexão."""
        copia = copy.copy(self)
        copia.conversa = conversa
        return copia

    async def fechar(self) -> None:
        await self._http.aclose()

    async def _pedir(self, metodo: str, caminho: str, **kwargs: Any) -> Any:
        if self.conversa:
            kwargs["headers"] = {**kwargs.get("headers", {}), "X-Conversa": self.conversa}
        try:
            resposta = await self._http.request(metodo, caminho, **kwargs)
        except httpx.HTTPError as erro:
            raise ErroApi(0, "sem_conexao", SEM_CONEXAO) from erro
        if resposta.is_success:
            return resposta.json() if resposta.content else None
        try:
            corpo = resposta.json()
            codigo, mensagem = corpo["erro"], corpo["mensagem"]
        except (ValueError, KeyError, TypeError):
            codigo, mensagem = "erro_http", f"A plataforma respondeu {resposta.status_code}."
        raise ErroApi(resposta.status_code, codigo, mensagem)

    # ------------------------------------------------------------ leitura

    async def saude(self) -> dict[str, Any]:
        resultado: dict[str, Any] = await self._pedir("GET", "/api/saude")
        return resultado

    async def fazendas(self) -> list[dict[str, Any]]:
        resultado: list[dict[str, Any]] = await self._pedir("GET", "/api/fazendas")
        return resultado

    async def cultivos_da_fazenda(self, fazenda_id: int) -> list[dict[str, Any]]:
        resultado: list[dict[str, Any]] = await self._pedir(
            "GET", f"/api/fazendas/{fazenda_id}/cultivos"
        )
        return resultado

    async def cultivo(self, cultivo_id: int) -> dict[str, Any]:
        resultado: dict[str, Any] = await self._pedir("GET", f"/api/cultivos/{cultivo_id}")
        return resultado

    async def resumo(self, cultivo_id: int) -> dict[str, Any]:
        resultado: dict[str, Any] = await self._pedir("GET", f"/api/cultivos/{cultivo_id}/resumo")
        return resultado

    async def diarios(self, cultivo_id: int, de: str | None = None) -> list[dict[str, Any]]:
        params = {"de": de} if de else None
        resultado: list[dict[str, Any]] = await self._pedir(
            "GET", f"/api/cultivos/{cultivo_id}/diarios", params=params
        )
        return resultado

    async def irrigacoes(self, cultivo_id: int, de: str | None = None) -> list[dict[str, Any]]:
        params = {"de": de} if de else None
        resultado: list[dict[str, Any]] = await self._pedir(
            "GET", f"/api/cultivos/{cultivo_id}/irrigacoes", params=params
        )
        return resultado

    # ------------------------------------------------------------ válvula

    async def enviar_comando(
        self, serial: str, acao: str, minutos: float | None = None
    ) -> dict[str, Any]:
        corpo: dict[str, Any] = {"acao": acao}
        if minutos is not None:
            corpo["minutos"] = minutos
        resultado: dict[str, Any] = await self._pedir(
            "POST", f"/api/dispositivos/{serial}/comandos", json=corpo
        )
        return resultado

    async def comandos(self, serial: str) -> list[dict[str, Any]]:
        resultado: list[dict[str, Any]] = await self._pedir(
            "GET", f"/api/dispositivos/{serial}/comandos"
        )
        return resultado

    # ------------------------------------------------------------ vínculo de conversas

    async def registrar_bot(self, canal: str, usuario_bot: str) -> None:
        """Informa à plataforma o @ do bot (o painel monta o link do QR code com ele)."""
        await self._pedir("PUT", f"/api/canais/{canal}/bot", json={"usuario_bot": usuario_bot})

    async def vincular(
        self, canal: str, codigo: str, conversa_id: str, nome: str | None
    ) -> dict[str, Any]:
        resultado: dict[str, Any] = await self._pedir(
            "POST",
            f"/api/canais/{canal}/vincular",
            json={"codigo": codigo, "conversa_id": conversa_id, "nome": nome},
        )
        return resultado

    async def conversas(self, canal: str) -> list[dict[str, Any]]:
        """Todas as conversas vinculadas do canal (só o token do chatbot)."""
        resultado: list[dict[str, Any]] = await self._pedir("GET", f"/api/canais/{canal}/conversas")
        return resultado

    async def conversa_atual(self) -> dict[str, Any]:
        """A conversa de `como(...)`: dono, alertas e cultivo escolhido."""
        resultado: dict[str, Any] = await self._pedir("GET", "/api/canais/conversa")
        return resultado

    async def editar_conversa(self, **campos: Any) -> dict[str, Any]:
        resultado: dict[str, Any] = await self._pedir("PATCH", "/api/canais/conversa", json=campos)
        return resultado

    async def desconectar_conversa(self) -> None:
        await self._pedir("DELETE", "/api/canais/conversa")
