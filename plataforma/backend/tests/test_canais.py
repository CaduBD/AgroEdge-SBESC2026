"""Vínculo de conversas do chatbot: QR code no painel, /start no bot, X-Conversa e SSE."""

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlmodel import select

from app.auth import gerar_hash_senha, gerar_hash_token
from app.eventos import Evento
from app.models import (
    CodigoVinculo,
    EscopoToken,
    Fazenda,
    TokenServico,
    Usuario,
    VinculoCanal,
    agora_utc,
)
from tests.test_api import SENHA, TOKEN, ctx  # noqa: F401  (fixture)

CHATBOT = {"Authorization": f"Bearer {TOKEN}"}
TOKEN_COMUM = "token-de-outro-servico-qualquer"


@pytest.fixture
async def c(ctx) -> AsyncIterator[dict]:  # noqa: F811
    """O token do ctx passa a ser o do chatbot; há um segundo usuário (Bia) com fazenda."""
    async with ctx["fabrica"]() as s:
        token = (await s.execute(select(TokenServico))).scalar_one()
        token.escopo = EscopoToken.chatbot
        bia = Usuario(nome="Bia", email="bia@teste", senha_hash=gerar_hash_senha(SENHA))
        s.add_all([token, bia])
        await s.flush()
        s.add(Fazenda(usuario_id=bia.id, nome="Sítio da Bia"))
        s.add(
            TokenServico(usuario_id=bia.id, nome="outro", token_hash=gerar_hash_token(TOKEN_COMUM))
        )
        await s.commit()
        ctx["bia"] = bia
    yield ctx


async def login(cliente, email: str) -> None:
    r = await cliente.post("/api/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 200, r.text


async def registrar_bot(cliente) -> None:
    r = await cliente.put(
        "/api/canais/telegram/bot", json={"usuario_bot": "agroedge_bot"}, headers=CHATBOT
    )
    assert r.status_code == 200, r.text


async def conectar(cliente, email: str, conversa: str, nome: str = "Produtor") -> dict:
    """Faz o caminho completo: login no painel → QR code → /start <codigo> no bot."""
    await login(cliente, email)
    codigo = (await cliente.post("/api/canais/telegram/codigo")).json()
    await cliente.post("/api/auth/logout")
    r = await cliente.post(
        "/api/canais/telegram/vincular",
        json={"codigo": codigo["codigo"], "conversa_id": conversa, "nome": nome},
        headers=CHATBOT,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- painel


async def test_painel_sem_bot_ligado(c):
    cliente = c["cliente"]
    await login(cliente, "equipe@teste")
    assert (await cliente.get("/api/canais/telegram")).json() == {
        "canal": "telegram",
        "usuario_bot": None,
    }
    r = await cliente.post("/api/canais/telegram/codigo")
    assert r.status_code == 409 and r.json()["erro"] == "bot_desligado"


async def test_codigo_e_link_do_qr(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await login(cliente, "equipe@teste")
    assert (await cliente.get("/api/canais/telegram")).json()["usuario_bot"] == "agroedge_bot"
    r = await cliente.post("/api/canais/telegram/codigo")
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["link"] == f"https://t.me/agroedge_bot?start={corpo['codigo']}"
    assert (
        len(corpo["codigo"]) <= 64 and corpo["codigo"].replace("-", "").replace("_", "").isalnum()
    )
    assert corpo["expira_em"].endswith("Z")


async def test_canal_desconhecido(c):
    await login(c["cliente"], "equipe@teste")
    assert (await c["cliente"].post("/api/canais/sms/codigo")).status_code == 422


# ---------------------------------------------------------------- vincular


async def test_vincular_pelo_codigo(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    conversa = await conectar(cliente, "equipe@teste", "1150177387", "Cadu (@cadu)")
    assert conversa == {
        "canal": "telegram", "conversa_id": "1150177387", "usuario_id": c["usuario"].id,
        "usuario_nome": "Equipe", "alertas": True, "cultivo_id": None,
    }  # fmt: skip
    await login(cliente, "equipe@teste")
    lista = (await cliente.get("/api/canais/vinculos")).json()
    assert [(v["canal"], v["nome"]) for v in lista] == [("telegram", "Cadu (@cadu)")]


async def test_painel_ve_quando_o_codigo_foi_usado(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await login(cliente, "equipe@teste")
    codigo = (await cliente.post("/api/canais/telegram/codigo")).json()["codigo"]
    r = (await cliente.get(f"/api/canais/codigos/{codigo}")).json()
    assert r["usado_em"] is None and r["vinculo"] is None
    await cliente.post(
        "/api/canais/telegram/vincular",
        json={"codigo": codigo, "conversa_id": "5", "nome": "Cadu"},
        headers=CHATBOT,
    )
    r = (await cliente.get(f"/api/canais/codigos/{codigo}")).json()
    assert r["usado_em"] and r["vinculo"]["nome"] == "Cadu"
    # código de outro usuário não aparece
    await cliente.post("/api/auth/logout")
    await login(cliente, "bia@teste")
    assert (await cliente.get(f"/api/canais/codigos/{codigo}")).status_code == 404


async def test_codigo_vale_uma_vez(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await login(cliente, "equipe@teste")
    codigo = (await cliente.post("/api/canais/telegram/codigo")).json()["codigo"]
    corpo = {"codigo": codigo, "conversa_id": "1"}
    url = "/api/canais/telegram/vincular"
    assert (await cliente.post(url, json=corpo, headers=CHATBOT)).status_code == 200
    r = await cliente.post(url, json=corpo | {"conversa_id": "2"}, headers=CHATBOT)
    assert r.status_code == 409 and r.json()["erro"] == "codigo_usado"


async def test_codigo_vencido_e_invalido(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    async with c["fabrica"]() as s:
        s.add(
            CodigoVinculo(
                codigo="vencido123", usuario_id=c["usuario"].id, canal="telegram",
                expira_em=agora_utc() - timedelta(minutes=1),
            )
        )  # fmt: skip
        await s.commit()
    url = "/api/canais/telegram/vincular"
    r = await cliente.post(url, json={"codigo": "vencido123", "conversa_id": "1"}, headers=CHATBOT)
    assert r.status_code == 410 and r.json()["erro"] == "codigo_expirado"
    r = await cliente.post(url, json={"codigo": "naoexiste", "conversa_id": "1"}, headers=CHATBOT)
    assert r.status_code == 404 and r.json()["erro"] == "codigo_invalido"


async def test_so_o_token_do_chatbot_vincula(c):
    cliente = c["cliente"]
    url = "/api/canais/telegram/vincular"
    corpo = {"codigo": "x" * 10, "conversa_id": "1"}
    assert (await cliente.post(url, json=corpo)).status_code == 401
    r = await cliente.post(url, json=corpo, headers={"Authorization": f"Bearer {TOKEN_COMUM}"})
    assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
    await login(cliente, "equipe@teste")  # nem o usuário logado
    assert (await cliente.post(url, json=corpo)).status_code == 401


async def test_conversa_muda_de_conta(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await conectar(cliente, "equipe@teste", "77")
    conversa = await conectar(cliente, "bia@teste", "77")
    assert conversa["usuario_nome"] == "Bia"
    async with c["fabrica"]() as s:
        assert len((await s.execute(select(VinculoCanal))).scalars().all()) == 1


# ---------------------------------------------------------------- X-Conversa


async def test_conversa_age_como_o_dono(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await conectar(cliente, "equipe@teste", "100")
    await conectar(cliente, "bia@teste", "200")

    def com(conversa):
        return CHATBOT | {"X-Conversa": f"telegram:{conversa}"}

    equipe = (await cliente.get("/api/fazendas", headers=com("100"))).json()
    bia = (await cliente.get("/api/fazendas", headers=com("200"))).json()
    assert [f["nome"] for f in equipe] == ["Fazenda"]
    assert [f["nome"] for f in bia] == ["Sítio da Bia"]
    # Bia não enxerga o cultivo da equipe (mesma regra do painel: 404)
    r = await cliente.get(f"/api/cultivos/{c['uva'].id}/resumo", headers=com("200"))
    assert r.status_code == 404


async def test_conversa_desconhecida_e_formato(c):
    cliente = c["cliente"]
    r = await cliente.get("/api/fazendas", headers=CHATBOT | {"X-Conversa": "telegram:999"})
    assert r.status_code == 403 and r.json()["erro"] == "conversa_nao_vinculada"
    r = await cliente.get("/api/fazendas", headers=CHATBOT | {"X-Conversa": "sms:1"})
    assert r.status_code == 400 and r.json()["erro"] == "conversa_invalida"
    comum = {"Authorization": f"Bearer {TOKEN_COMUM}", "X-Conversa": "telegram:1"}
    r = await cliente.get("/api/fazendas", headers=comum)
    assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"


async def test_preferencias_da_conversa(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await conectar(cliente, "equipe@teste", "100")
    h = CHATBOT | {"X-Conversa": "telegram:100"}
    r = await cliente.patch(
        "/api/canais/conversa", json={"alertas": False, "cultivo_id": c["uva"].id}, headers=h
    )
    assert r.status_code == 200
    assert (r.json()["alertas"], r.json()["cultivo_id"]) == (False, c["uva"].id)
    assert (await cliente.get("/api/canais/conversa", headers=h)).json()["cultivo_id"] == c[
        "uva"
    ].id
    r = await cliente.patch("/api/canais/conversa", json={"cultivo_id": 0}, headers=h)
    assert r.json()["cultivo_id"] is None
    # cultivo que não é do dono da conversa
    await conectar(cliente, "bia@teste", "200")
    h_bia = CHATBOT | {"X-Conversa": "telegram:200"}
    r = await cliente.patch("/api/canais/conversa", json={"cultivo_id": c["uva"].id}, headers=h_bia)
    assert r.status_code == 404
    # sem X-Conversa não há "conversa atual"
    r = await cliente.get("/api/canais/conversa", headers=CHATBOT)
    assert r.status_code == 400 and r.json()["erro"] == "sem_conversa"


async def test_lista_de_conversas_para_o_bot(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await conectar(cliente, "equipe@teste", "100")
    await conectar(cliente, "bia@teste", "200")
    lista = (await cliente.get("/api/canais/telegram/conversas", headers=CHATBOT)).json()
    assert [(x["conversa_id"], x["usuario_nome"]) for x in lista] == [
        ("100", "Equipe"),
        ("200", "Bia"),
    ]
    await login(cliente, "equipe@teste")
    assert (await cliente.get("/api/canais/telegram/conversas")).status_code == 401


# ---------------------------------------------------------------- desconectar


async def test_desconectar_pelo_painel(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await conectar(cliente, "equipe@teste", "100")
    await conectar(cliente, "bia@teste", "200")
    await login(cliente, "equipe@teste")
    meu = (await cliente.get("/api/canais/vinculos")).json()[0]
    await cliente.post("/api/auth/logout")
    await login(cliente, "bia@teste")
    assert (await cliente.delete(f"/api/canais/vinculos/{meu['id']}")).status_code == 404
    await cliente.post("/api/auth/logout")
    await login(cliente, "equipe@teste")
    assert (await cliente.delete(f"/api/canais/vinculos/{meu['id']}")).status_code == 204
    r = await cliente.get("/api/fazendas", headers=CHATBOT | {"X-Conversa": "telegram:100"})
    assert r.status_code == 403


async def test_desconectar_pelo_bot(c):
    cliente = c["cliente"]
    await registrar_bot(cliente)
    await conectar(cliente, "equipe@teste", "100")
    h = CHATBOT | {"X-Conversa": "telegram:100"}
    assert (await cliente.delete("/api/canais/conversa", headers=h)).status_code == 204
    assert (await cliente.get("/api/canais/conversa", headers=h)).status_code == 403


# ---------------------------------------------------------------- SSE


async def test_dono_do_evento_para_o_sse_de_todos(c, monkeypatch):
    import app.rotas.stream as stream

    monkeypatch.setattr(stream, "fabrica_sessao", c["fabrica"])
    _dono = stream._dono

    assert await _dono(Evento("status", "agroedge-00001", None, {})) == c["usuario"].id
    assert await _dono(Evento("diario", "placa-sem-dono", c["uva"].id, {})) == c["usuario"].id
    assert await _dono(Evento("status", "placa-sem-dono", None, {})) is None


async def test_sse_de_todos_so_com_token_do_chatbot(c):
    cliente = c["cliente"]
    r = await cliente.get(
        "/api/stream?todos=true", headers={"Authorization": f"Bearer {TOKEN_COMUM}"}
    )
    assert r.status_code == 403 and r.json()["erro"] == "escopo_insuficiente"
