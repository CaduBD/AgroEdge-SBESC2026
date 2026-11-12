"""Conversa conectada pela plataforma (QR code do painel → /start <codigo>), como no Telegram."""

import asyncio

from agroedge_bot.nucleo.servico import Servico
from agroedge_bot.nucleo.sse import EventoSse
from tests.conftest import Caixa, PlataformaFalsa, resumo_exemplo


def dados_dos_botoes(resposta) -> list[str]:
    return [b.dado for linha in resposta.botoes for b in linha]


async def conectar(servico: Servico, plataforma: PlataformaFalsa, conversa: str, usuario: int = 1):
    codigo = f"Codigo{conversa}"
    plataforma.codigos[codigo] = usuario
    return await servico.tratar_texto(conversa, f"/start {codigo}", nome="Produtor")


async def test_sem_conexao_so_explica_como_conectar(servico_plat: Servico, plataforma) -> None:
    r = await servico_plat.tratar_texto("555", "hoje")
    assert "Conectar Telegram" in r.texto and r.menu is False
    # só perguntou à plataforma quem é a conversa; nada de dados
    assert [p.url.path for p in plataforma.pedidos] == ["/api/canais/conversa"]


async def test_start_com_codigo_conecta_e_respeita_maiusculas(servico_plat, plataforma) -> None:
    plataforma.codigos["AbCdEf_12-3"] = 1
    r = await servico_plat.tratar_texto("555", "/start AbCdEf_12-3", nome="Carlos (@cadu)")
    assert "conectada à conta de <b>Equipe</b>" in r.texto and r.menu
    assert plataforma.vinculos["555"]["nome"] == "Carlos (@cadu)"
    assert "Estado hídrico" in (await servico_plat.tratar_texto("555", "hoje")).texto


async def test_codigo_vencido(servico_plat: Servico) -> None:
    r = await servico_plat.tratar_texto("555", "/start naoexiste")
    assert r.texto == "❌ Este QR code venceu. Gere outro no painel." and r.menu is False


async def test_pedidos_vao_em_nome_da_conversa(servico_plat, plataforma) -> None:
    await conectar(servico_plat, plataforma, "555")
    plataforma.pedidos.clear()
    await servico_plat.tratar_texto("555", "hoje")
    assert plataforma.pedidos
    assert all(p.headers["X-Conversa"] == "telegram:555" for p in plataforma.pedidos)


async def test_cada_conta_ve_o_seu(servico_plat, plataforma) -> None:
    await conectar(servico_plat, plataforma, "555", usuario=1)
    await conectar(servico_plat, plataforma, "777", usuario=2)
    assert "Bancada uva" in (await servico_plat.tratar_texto("555", "hoje")).texto
    assert "Não encontrei nenhum cultivo" in (await servico_plat.tratar_texto("777", "hoje")).texto


async def test_escolhas_ficam_na_plataforma(servico_plat, plataforma) -> None:
    await conectar(servico_plat, plataforma, "555")
    await servico_plat.tratar_texto("555", "hoje")
    assert plataforma.vinculos["555"]["cultivo_id"] == 2
    await servico_plat.tratar_botao("555", "al:0")
    assert plataforma.vinculos["555"]["alertas"] is False


async def test_desconectar_pelo_bot(servico_plat, plataforma) -> None:
    await conectar(servico_plat, plataforma, "555")
    r = await servico_plat.tratar_texto("555", "desconectar")
    assert dados_dos_botoes(r) == ["dc", "no"]
    assert "555" in plataforma.vinculos  # só depois da confirmação
    r = await servico_plat.tratar_botao("555", "dc")
    assert "desconectada" in r.texto and r.menu is False
    assert "555" not in plataforma.vinculos
    assert "Conectar Telegram" in (await servico_plat.tratar_texto("555", "hoje")).texto


async def test_desconectada_pelo_painel_no_meio_da_conversa(servico_plat, plataforma) -> None:
    await conectar(servico_plat, plataforma, "555")
    r = await servico_plat.tratar_texto("555", "abrir 10")
    del plataforma.vinculos["555"]  # alguém desconectou pelo painel
    r = await servico_plat.tratar_botao("555", dados_dos_botoes(r)[0])
    assert "Conectar Telegram" in r.texto
    assert plataforma.comandos == []


async def test_alerta_vai_so_para_as_conversas_do_dono(
    servico_plat: Servico, plataforma: PlataformaFalsa, caixa: Caixa
) -> None:
    await conectar(servico_plat, plataforma, "555", usuario=1)
    await conectar(servico_plat, plataforma, "556", usuario=1)
    await conectar(servico_plat, plataforma, "777", usuario=2)
    plataforma.vinculos["556"]["alertas"] = False
    plataforma.diarios = [resumo_exemplo()["ultimo_diario"] | {"data": "2026-11-11"}]
    evento = {"serial": "agroedge-00001", "cultivo_id": 2, "usuario_id": 1, "data": "2026-11-11"}
    await servico_plat.ao_evento(EventoSse("diario", evento))
    assert [c for c, _ in caixa.enviadas] == ["555"]
    # o fechamento completo foi buscado em nome de uma conversa do dono
    busca = [p for p in plataforma.pedidos if p.url.path.endswith("/diarios")][-1]
    assert busca.headers["X-Conversa"] in ("telegram:555", "telegram:556")


async def test_evento_de_conta_sem_conversa_nao_avisa(servico_plat, plataforma, caixa) -> None:
    await conectar(servico_plat, plataforma, "777", usuario=2)
    evento = {"serial": "s", "cultivo_id": 2, "usuario_id": 1, "status": "offline"}
    await servico_plat.ao_evento(EventoSse("status", evento))
    assert caixa.enviadas == []


async def test_resposta_do_comando_volta_para_quem_pediu(servico_plat, plataforma, caixa) -> None:
    await conectar(servico_plat, plataforma, "555")
    r = await servico_plat.tratar_texto("555", "abrir 10")
    await servico_plat.tratar_botao("555", dados_dos_botoes(r)[0])
    plataforma.comandos[0] |= {"estado": "executado", "resultado": "executado"}
    for _ in range(100):
        if caixa.enviadas:
            break
        await asyncio.sleep(0.01)
    assert caixa.enviadas[0][0] == "555" and "aberta por 10 min" in caixa.textos[0]
    consulta = [p for p in plataforma.pedidos if p.url.path.endswith("/comandos")][-1]
    assert consulta.headers["X-Conversa"] == "telegram:555"


async def test_sincronizar_por_conta(servico_plat, plataforma, caixa) -> None:
    await conectar(servico_plat, plataforma, "555", usuario=1)
    await conectar(servico_plat, plataforma, "777", usuario=2)
    await servico_plat.sincronizar()
    assert servico_plat.estado.ultimo_diario == {"2": "2026-11-10"}
    novo = resumo_exemplo()
    novo["ultimo_diario"]["data"] = "2026-11-11"
    plataforma.resumos[2] = novo
    await servico_plat.ao_reconectar()
    assert [c for c, _ in caixa.enviadas] == ["555"]
