import asyncio
import json

from agroedge_bot.nucleo.acesso import AcessoLocal
from agroedge_bot.nucleo.estado import Estado
from agroedge_bot.nucleo.servico import Servico, normalizar
from agroedge_bot.nucleo.sse import EventoSse
from tests.conftest import Caixa, PlataformaFalsa, Relogio, resumo_exemplo


def dados_dos_botoes(resposta) -> list[str]:
    return [b.dado for linha in resposta.botoes for b in linha]


# ---------------------------------------------------------------- acesso e texto


async def test_conversa_de_fora_nao_ve_nada(servico: Servico, plataforma: PlataformaFalsa) -> None:
    r = await servico.tratar_texto("999", "hoje")
    assert "não está conectada" in r.texto and r.menu is False
    r = await servico.tratar_botao("999", "ok:a:2:10:1794438000")
    assert "não está conectada" in r.texto
    assert plataforma.pedidos == []  # nem chegou a consultar a API


def test_normalizar() -> None:
    assert normalizar("  Válvula ") == "valvula"
    assert normalizar("Histórico") == "historico"


async def test_comandos_escritos_de_varios_jeitos(servico: Servico) -> None:
    for texto in ("/hoje", "Hoje", "/hoje@AgroEdgeBot", "resumo"):
        r = await servico.tratar_texto("100", texto)
        assert "Estado hídrico" in r.texto, texto
    assert "Não entendi" in (await servico.tratar_texto("100", "blablabla")).texto
    assert "irrigação de precisão" in (await servico.tratar_texto("100", "/start")).texto


async def test_erro_da_api_vira_mensagem(servico: Servico, plataforma: PlataformaFalsa) -> None:
    api = servico.acesso.api("100")
    api._http.headers["Authorization"] = "Bearer errado"
    r = await servico.tratar_texto("100", "hoje")
    assert r.texto == "❌ Token inválido."


# ---------------------------------------------------------------- cultivos


async def test_um_cultivo_e_escolhido_sozinho(servico: Servico) -> None:
    await servico.tratar_texto("100", "hoje")
    assert servico.estado.conversa("100").cultivo_id == 2


async def test_varios_cultivos_pergunta_qual(servico: Servico, plataforma: PlataformaFalsa) -> None:
    plataforma.cultivos.append({"id": 5, "nome": "Pomar manga", "ultima_classe": 1})
    r = await servico.tratar_texto("100", "historico")
    assert r.texto == "De qual cultivo?"
    assert dados_dos_botoes(r) == ["sel:hist:2", "sel:hist:5"]
    r = await servico.tratar_botao("100", "sel:hist:5")
    assert "Pomar manga" in r.texto
    assert servico.estado.conversa("100").cultivo_id == 5
    # escolha lembrada (e cada conversa tem a sua)
    assert "Pomar manga" in (await servico.tratar_texto("100", "hoje")).texto
    assert (await servico.tratar_texto("200", "hoje")).texto == "De qual cultivo?"


async def test_cultivo_por_numero_e_lista(servico: Servico, plataforma: PlataformaFalsa) -> None:
    plataforma.cultivos.append({"id": 5, "nome": "Pomar manga", "ultima_classe": 1})
    r = await servico.tratar_texto("100", "cultivos")
    assert "1. Bancada uva" in r.texto and "2. Pomar manga" in r.texto
    r = await servico.tratar_texto("100", "cultivos 2")
    assert "Pomar manga" in r.texto
    assert "Não há cultivo número 7" in (await servico.tratar_texto("100", "cultivos 7")).texto


async def test_cultivo_que_sumiu_pede_de_novo(
    servico: Servico, plataforma: PlataformaFalsa
) -> None:
    servico.estado.conversa("100").cultivo_id = 99  # p.ex. estado de outro banco
    r = await servico.tratar_texto("100", "hoje")
    assert "Bancada uva" in r.texto  # só há um: escolhido de novo sozinho


# ---------------------------------------------------------------- válvula


async def test_painel_da_valvula(servico: Servico) -> None:
    r = await servico.tratar_texto("100", "válvula")
    dados = dados_dos_botoes(r)
    assert "v:a:2:10" in dados and "v:f:2" in dados
    assert "v:a:2:357" not in dados  # indicado (357 min) passa de 120: sem atalho


async def test_painel_sem_placa_nao_oferece_abrir(
    servico: Servico, plataforma: PlataformaFalsa
) -> None:
    plataforma.resumos[2] = resumo_exemplo(com_placa=False)
    r = await servico.tratar_texto("100", "valvula")
    assert not any(d.startswith("v:") for d in dados_dos_botoes(r))
    assert "Nenhuma placa instalada" in r.texto


async def test_abrir_pede_confirmacao_e_envia(
    servico: Servico, plataforma: PlataformaFalsa, caixa: Caixa
) -> None:
    r = await servico.tratar_texto("100", "abrir 10")
    assert r.texto == "Abrir a válvula de <b>Bancada uva</b> por <b>10 min</b>?"
    sim, nao = dados_dos_botoes(r)
    assert sim == "ok:a:2:10:1794438000" and nao == "no"
    assert plataforma.comandos == []  # nada enviado antes do "Sim"

    r = await servico.tratar_botao("100", sim)
    assert "Aguardando a placa" in r.texto
    assert plataforma.comandos[0] | {} == {
        "id": "cmd-1",
        "acao": "abrir",
        "minutos": 10.0,
        "estado": "enviado",
        "resultado": None,
    }
    post = next(p for p in plataforma.pedidos if p.method == "POST")
    assert post.url.path == "/api/dispositivos/agroedge-00001/comandos"  # serial vem do resumo
    assert json.loads(post.content) == {"acao": "abrir", "minutos": 10.0}

    # a placa responde pelo SSE → quem pediu recebe a confirmação
    await servico.ao_evento(
        EventoSse(
            "comando",
            {
                "serial": "agroedge-00001",
                "cultivo_id": 2,
                "id": "cmd-1",
                "estado": "executado",
                "resultado": "executado",
            },
        )
    )
    assert caixa.enviadas[-1][0] == "100"
    assert "aberta por 10 min" in caixa.enviadas[-1][1].texto


async def test_toque_duplo_nao_envia_dois(servico: Servico, plataforma: PlataformaFalsa) -> None:
    sim = dados_dos_botoes(await servico.tratar_texto("100", "abrir 10"))[0]
    await servico.tratar_botao("100", sim)
    r = await servico.tratar_botao("100", sim)
    assert r.texto == "Esse comando já foi enviado."
    assert len(plataforma.comandos) == 1


async def test_confirmacao_vence(
    servico: Servico, relogio: Relogio, plataforma: PlataformaFalsa
) -> None:
    sim = dados_dos_botoes(await servico.tratar_texto("100", "abrir 10"))[0]
    relogio.agora += 121
    r = await servico.tratar_botao("100", sim)
    assert "venceu" in r.texto
    assert plataforma.comandos == []


async def test_nao_cancela(servico: Servico, plataforma: PlataformaFalsa) -> None:
    r = await servico.tratar_botao("100", "no")
    assert "nada foi feito" in r.texto
    assert plataforma.comandos == []


async def test_minutos_fora_do_limite(servico: Servico) -> None:
    assert "de 1 a 120" in (await servico.tratar_texto("100", "abrir 500")).texto
    assert "de 1 a 120" in (await servico.tratar_texto("100", "abrir 0")).texto
    r = await servico.tratar_texto("100", "abrir 2,5")
    assert "<b>2,5 min</b>" in r.texto
    # sem minutos: mostra o painel
    assert "v:a:2:10" in dados_dos_botoes(await servico.tratar_texto("100", "abrir"))


async def test_fechar(servico: Servico, plataforma: PlataformaFalsa) -> None:
    r = await servico.tratar_texto("100", "fechar")
    assert "Fechar a válvula" in r.texto
    await servico.tratar_botao("100", dados_dos_botoes(r)[0])
    assert (
        plataforma.comandos[0]["acao"] == "cancelar" and plataforma.comandos[0]["minutos"] is None
    )


async def test_placa_offline_mostra_erro_e_deixa_tentar_de_novo(
    servico: Servico, plataforma: PlataformaFalsa
) -> None:
    plataforma.erro_comando = (
        409,
        "dispositivo_offline",
        "A placa está sem contato há mais de 10 minutos.",
    )
    sim = dados_dos_botoes(await servico.tratar_texto("100", "abrir 10"))[0]
    r = await servico.tratar_botao("100", sim)
    assert r.texto == "❌ A placa está sem contato há mais de 10 minutos."
    plataforma.erro_comando = None
    r = await servico.tratar_botao("100", sim)
    assert "Aguardando a placa" in r.texto


async def test_sem_sse_a_resposta_vem_pela_api(
    servico: Servico, plataforma: PlataformaFalsa, caixa: Caixa
) -> None:
    sim = dados_dos_botoes(await servico.tratar_texto("100", "abrir 10"))[0]
    await servico.tratar_botao("100", sim)
    plataforma.comandos[0] |= {"estado": "recusado", "resultado": "recusado_em_andamento"}
    for _ in range(100):
        if caixa.enviadas:
            break
        await asyncio.sleep(0.01)
    assert "já havia uma irrigação em andamento" in caixa.textos[0]
    # evento atrasado do SSE não repete o aviso
    await servico.ao_evento(EventoSse("comando", {"id": "cmd-1", "estado": "recusado"}))
    assert len(caixa.enviadas) == 1


async def test_comando_do_painel_e_ignorado(servico: Servico, caixa: Caixa) -> None:
    await servico.ao_evento(EventoSse("comando", {"id": "outro", "estado": "executado"}))
    assert caixa.enviadas == []


# ---------------------------------------------------------------- alertas


async def test_alerta_diario_para_quem_quer(
    servico: Servico, plataforma: PlataformaFalsa, caixa: Caixa
) -> None:
    servico.estado.conversa("200").alertas = False
    plataforma.diarios = [resumo_exemplo()["ultimo_diario"] | {"data": "2026-11-11"}]
    evento = EventoSse(
        "diario",
        {
            "serial": "agroedge-00001",
            "cultivo_id": 2,
            "data": "2026-11-11",
            "lamina_bruta": 11.9,
            "minutos": 357.0,
            "classe": 0,
        },
    )
    await servico.ao_evento(evento)
    assert [c for c, _ in caixa.enviadas] == ["100"]
    assert "47,6 L/planta" in caixa.textos[0]  # veio do fechamento completo
    ver_hoje = caixa.enviadas[0][1].botoes[0][0].dado
    assert ver_hoje == "n:hoje:2"
    assert (await servico.tratar_botao("100", ver_hoje)).nova_mensagem is True  # não apaga o alerta
    assert (await servico.tratar_botao("100", "sel:hoje:2")).nova_mensagem is False
    await servico.ao_evento(evento)  # repetido: não avisa de novo
    assert len(caixa.enviadas) == 1


async def test_sincronizar_primeira_vez_nao_avisa_depois_avisa(
    servico: Servico, plataforma: PlataformaFalsa, caixa: Caixa
) -> None:
    await servico.sincronizar()
    assert caixa.enviadas == []
    assert servico.estado.ultimo_diario == {"2": "2026-11-10"}
    # o bot ficou desconectado e perdeu o fechamento do dia 11
    novo = resumo_exemplo()
    novo["ultimo_diario"]["data"] = "2026-11-11"
    plataforma.resumos[2] = novo
    await servico.ao_reconectar()
    assert len(caixa.enviadas) == 2 and "Fechamento de 11/11" in caixa.textos[0]


async def test_status_so_avisa_quando_muda(servico: Servico, caixa: Caixa) -> None:
    def ev(s: str) -> EventoSse:
        return EventoSse("status", {"serial": "agroedge-00001", "cultivo_id": 2, "status": s})

    await servico.ao_evento(ev("online"))  # primeira notícia: nada
    assert caixa.enviadas == []
    await servico.ao_evento(ev("offline"))
    await servico.ao_evento(ev("offline"))
    await servico.ao_evento(ev("online"))
    assert len(caixa.textos) == 4  # 2 conversas × (offline + online)
    assert "sem contato" in caixa.textos[0] and "voltou" in caixa.textos[2]


async def test_irrigacao_pedida_pelo_bot_nao_duplica(servico: Servico, caixa: Caixa) -> None:
    sim = dados_dos_botoes(await servico.tratar_texto("100", "abrir 10"))[0]
    await servico.tratar_botao("100", sim)
    inicio = {"serial": "agroedge-00001", "cultivo_id": 2, "estado": "iniciada", "origem": "manual"}
    await servico.ao_evento(EventoSse("irrigacao", inicio))
    assert caixa.enviadas == []
    await servico.ao_evento(
        EventoSse("irrigacao", inicio | {"origem": "automatica", "minutos": 30})
    )
    assert len(caixa.enviadas) == 2 and "automática começou" in caixa.textos[0]


async def test_tipos_de_alerta_desligados(api, caixa: Caixa, relogio: Relogio) -> None:
    estado = Estado()
    servico = Servico(
        AcessoLocal(api, {"100"}, estado), estado, caixa.enviar, alertas=set(), relogio=relogio
    )
    await servico.ao_evento(EventoSse("status", {"serial": "s", "status": "offline"}))
    await servico.ao_evento(
        EventoSse("irrigacao", {"serial": "s", "estado": "iniciada", "origem": "automatica"})
    )
    await servico.ao_evento(
        EventoSse("diario", {"serial": "s", "cultivo_id": 2, "data": "2026-11-11"})
    )
    assert caixa.enviadas == []


async def test_ligar_desligar_alertas(servico: Servico) -> None:
    r = await servico.tratar_texto("100", "alertas")
    assert "ligados" in r.texto and dados_dos_botoes(r) == ["al:0"]
    r = await servico.tratar_botao("100", "al:0")
    assert "desligados" in r.texto
    assert servico.estado.conversa("100").alertas is False
    await servico.tratar_texto("100", "alertas ligar")
    assert servico.estado.conversa("100").alertas is True


async def test_botao_desconhecido(servico: Servico) -> None:
    assert "não vale mais" in (await servico.tratar_botao("100", "xyz:1")).texto
    assert "não vale mais" in (await servico.tratar_botao("100", "sel:hoje:abc")).texto
