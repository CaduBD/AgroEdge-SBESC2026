"""Plataforma falsa (httpx.MockTransport) com as mesmas rotas e formatos da API real."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from agroedge_bot.nucleo.acesso import AcessoLocal, AcessoPlataforma
from agroedge_bot.nucleo.api import ClienteAgroEdge
from agroedge_bot.nucleo.estado import Estado
from agroedge_bot.nucleo.mensagens import Resposta
from agroedge_bot.nucleo.servico import Servico

TOKEN = "token-de-teste"


def resumo_exemplo(
    cid: int = 2, nome: str = "Bancada uva", com_placa: bool = True
) -> dict[str, Any]:
    return {
        "cultivo": {
            "id": cid,
            "nome": nome,
            "cultura": "uva_italia",
            "cultura_info": {"nome": "Uva de mesa cv. Itália"},
            "fazenda": {"id": 1, "nome": "Fazenda Exemplo"},
        },
        "dispositivo": {
            "serial": "agroedge-00001",
            "apelido": None,
            "status": "ao_vivo",
            "sincronizando": 0,
            "ultima_telemetria": "2026-11-11T23:00:00Z",
            "ultimo_contato": "2026-11-11T23:00:42Z",
            "bat_v": None,
            "rssi": -61,
            "cfg_aplicada": True,
        }
        if com_placa
        else None,
        "ultima_leitura": {
            "ts": 1794438000, "temp_c": 31.6, "ur_pct": 47.5, "vento_ms": 4.2,
            "rad_wm2": 0.0, "chuva_mm": 0.0,
        },
        "ultimo_diario": {
            "data": "2026-11-10", "classe": 0, "lamina_bruta": 11.9, "minutos": 357.0,
            "aplicar_l_planta": 47.6, "et0": 6.28, "etc": 4.27, "kc": 0.68, "avisos": [],
        },
        "ciclo": {"dias": 22, "ciclo_dias": 109, "fora_do_ciclo": False, "fase": None,
                  "fase_nome": None},
        "valvula": {
            "aberta": False, "em_andamento": None,
            "proxima_prevista": "2026-11-12T08:00:00Z",
            "ultima": {"ts_inicio": 1794430245, "minutos": 1.0, "mm": 0.03, "origem": "manual"},
        },
        "ultimos_7_dias": [],
    }  # fmt: skip


@dataclass
class PlataformaFalsa:
    """Guarda o estado e responde às rotas que o bot usa."""

    cultivos: list[dict[str, Any]] = field(
        default_factory=lambda: [{"id": 2, "nome": "Bancada uva", "ultima_classe": 0}]
    )
    resumos: dict[int, dict[str, Any]] = field(default_factory=dict)
    diarios: list[dict[str, Any]] = field(default_factory=list)
    comandos: list[dict[str, Any]] = field(default_factory=list)
    erro_comando: tuple[int, str, str] | None = None
    pedidos: list[httpx.Request] = field(default_factory=list)
    # Vínculo de conversas (usuário 1 = dono dos cultivos acima; 2 = conta sem fazenda)
    bot: str | None = None
    codigos: dict[str, int] = field(default_factory=dict)  # código do QR → usuário
    vinculos: dict[str, dict[str, Any]] = field(default_factory=dict)  # conversa → vínculo
    USUARIOS = {1: "Equipe", 2: "Bia"}

    def _canais(self, req: httpx.Request, vinculo: dict[str, Any] | None) -> httpx.Response:
        caminho, metodo = req.url.path, req.method
        if caminho == "/api/canais/telegram/bot" and metodo == "PUT":
            self.bot = json.loads(req.content)["usuario_bot"]
            return httpx.Response(200, json={"canal": "telegram", "usuario_bot": self.bot})
        if caminho == "/api/canais/telegram/vincular":
            corpo = json.loads(req.content)
            usuario = self.codigos.pop(corpo["codigo"], None)
            if usuario is None:
                return httpx.Response(
                    410,
                    json={
                        "erro": "codigo_expirado",
                        "mensagem": "Este QR code venceu. Gere outro no painel.",
                    },
                )
            self.vinculos[corpo["conversa_id"]] = {
                "canal": "telegram", "conversa_id": corpo["conversa_id"], "usuario_id": usuario,
                "usuario_nome": self.USUARIOS[usuario], "alertas": True, "cultivo_id": None,
                "nome": corpo.get("nome"),
            }  # fmt: skip
            return httpx.Response(200, json=self.vinculos[corpo["conversa_id"]])
        if caminho == "/api/canais/telegram/conversas":
            return httpx.Response(200, json=list(self.vinculos.values()))
        if caminho == "/api/canais/conversa" and vinculo is not None:
            if metodo == "PATCH":
                corpo = json.loads(req.content)
                if "cultivo_id" in corpo:
                    vinculo["cultivo_id"] = corpo["cultivo_id"] or None
                if "alertas" in corpo:
                    vinculo["alertas"] = corpo["alertas"]
            if metodo == "DELETE":
                del self.vinculos[vinculo["conversa_id"]]
                return httpx.Response(204)
            return httpx.Response(200, json=vinculo)
        return httpx.Response(400, json={"erro": "sem_conversa", "mensagem": "Sem conversa."})

    def resposta(self, req: httpx.Request) -> httpx.Response:
        self.pedidos.append(req)
        if req.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(
                401, json={"erro": "token_invalido", "mensagem": "Token inválido."}
            )
        vinculo = None
        if "X-Conversa" in req.headers:
            vinculo = self.vinculos.get(req.headers["X-Conversa"].removeprefix("telegram:"))
            if vinculo is None:
                return httpx.Response(
                    403,
                    json={
                        "erro": "conversa_nao_vinculada",
                        "mensagem": "Esta conversa não está conectada a nenhuma conta AgroEdge.",
                    },
                )
        caminho = req.url.path
        if caminho.startswith("/api/canais/"):
            return self._canais(req, vinculo)
        if caminho == "/api/saude":
            return httpx.Response(200, json={"ok": True, "mqtt_conectado": True})
        if caminho == "/api/fazendas":
            if vinculo and vinculo["usuario_id"] != 1:
                return httpx.Response(200, json=[])  # a outra conta não tem fazendas
            return httpx.Response(200, json=[{"id": 1, "nome": "Fazenda Exemplo"}])
        if caminho == "/api/fazendas/1/cultivos":
            return httpx.Response(200, json=self.cultivos)
        partes = caminho.strip("/").split("/")
        if partes[:2] == ["api", "cultivos"]:
            cid = int(partes[2])
            c = next((c for c in self.cultivos if c["id"] == cid), None)
            if c is None:
                return httpx.Response(
                    404, json={"erro": "nao_encontrado", "mensagem": "Cultivo não encontrado."}
                )
            if len(partes) == 3:
                return httpx.Response(200, json=c)
            if partes[3] == "resumo":
                return httpx.Response(
                    200, json=self.resumos.get(cid) or resumo_exemplo(cid, c["nome"])
                )
            if partes[3] == "diarios":
                return httpx.Response(200, json=self.diarios)
            if partes[3] == "irrigacoes":
                return httpx.Response(200, json=[])
        if partes[:2] == ["api", "dispositivos"] and partes[3] == "comandos":
            if req.method == "POST":
                if self.erro_comando:
                    status, codigo, msg = self.erro_comando
                    return httpx.Response(status, json={"erro": codigo, "mensagem": msg})
                corpo = json.loads(req.content)
                comando = {
                    "id": f"cmd-{len(self.comandos) + 1}", "acao": corpo["acao"],
                    "minutos": corpo.get("minutos"), "estado": "enviado", "resultado": None,
                }  # fmt: skip
                self.comandos.append(comando)
                return httpx.Response(201, json=comando)
            return httpx.Response(200, json=list(reversed(self.comandos)))
        return httpx.Response(404, json={"erro": "nao_encontrado", "mensagem": "Rota?"})


@dataclass
class Caixa:
    """Mensagens que o núcleo mandou sem ser pedido (alertas, resposta de comando)."""

    enviadas: list[tuple[str, Resposta]] = field(default_factory=list)

    async def enviar(self, conversa: str, resposta: Resposta) -> None:
        self.enviadas.append((conversa, resposta))

    @property
    def textos(self) -> list[str]:
        return [r.texto for _, r in self.enviadas]


class Relogio:
    def __init__(self, agora: float = 1794438000.0) -> None:  # 11/11/2026 20:00 local
        self.agora = agora

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def plataforma() -> PlataformaFalsa:
    return PlataformaFalsa()


@pytest.fixture
def caixa() -> Caixa:
    return Caixa()


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
async def api(plataforma: PlataformaFalsa):
    cliente = ClienteAgroEdge(
        "http://plataforma", TOKEN, transporte=httpx.MockTransport(plataforma.resposta)
    )
    yield cliente
    await cliente.fechar()


@pytest.fixture
async def servico(api: ClienteAgroEdge, caixa: Caixa, relogio: Relogio, tmp_path):
    estado = Estado.carregar(tmp_path / "estado.json")
    s = Servico(
        AcessoLocal(api, {"100", "200"}, estado),
        estado,
        caixa.enviar,
        relogio=relogio,
        intervalo_consulta_s=0.01,
    )
    yield s
    await s.encerrar()


@pytest.fixture
async def servico_plat(api: ClienteAgroEdge, caixa: Caixa, relogio: Relogio, tmp_path):
    """Como no Telegram: quem pode usar o bot vem da plataforma (vínculo por QR code)."""
    s = Servico(
        AcessoPlataforma(api, "telegram"),
        Estado.carregar(tmp_path / "estado.json"),
        caixa.enviar,
        relogio=relogio,
        intervalo_consulta_s=0.01,
    )
    yield s
    await s.encerrar()
