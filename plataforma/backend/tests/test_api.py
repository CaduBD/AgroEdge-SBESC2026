"""Testes da API (seções 9 e 10): autenticação, posse, instalação, config, comandos, dados."""

import json
from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
from sqlmodel import col, select

import app.db as db
from app.auth import gerar_hash_senha, gerar_hash_token
from app.config import Settings
from app.db import obter_sessao
from app.limite_login import LimiteLogin
from app.main import app
from app.main import settings as settings_app
from app.models import (
    Comando,
    Cultivo,
    Dispositivo,
    EstadoComando,
    Fazenda,
    Instalacao,
    Leitura,
    StatusMqtt,
    TokenServico,
    Usuario,
    agora_utc,
    datetime_para_ts,
)
from app.rotas.auth import limite_login
from app.servicos.comandos import expirar_comandos
from app.servicos.ingestao import processar_mensagem
from tests.conftest import PublicadorFalso

SENHA = "senha-de-teste"
TOKEN = "token-de-teste-bem-longo"


@pytest.fixture
async def ctx(fabrica, base, monkeypatch) -> AsyncIterator[dict]:
    """Cliente HTTP do app com banco de teste, publicador falso, senha e token reais."""
    async with fabrica() as s:
        usuario = await s.get(Usuario, base["usuario"].id)
        usuario.senha_hash = gerar_hash_senha(SENHA)
        s.add(
            TokenServico(usuario_id=usuario.id, nome="chatbot", token_hash=gerar_hash_token(TOKEN))
        )
        await s.commit()

    async def _sessao():
        async with fabrica() as s:
            yield s

    app.dependency_overrides[obter_sessao] = _sessao
    monkeypatch.setattr(db, "fabrica_sessao", fabrica)
    publicador = PublicadorFalso()
    app.state.publicador = publicador
    limite_login.limpar()
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as cliente:
        yield {**base, "cliente": cliente, "pub": publicador, "fabrica": fabrica}
    app.dependency_overrides.clear()


@pytest.fixture
async def logado(ctx) -> dict:
    r = await ctx["cliente"].post("/api/auth/login", json={"email": "equipe@teste", "senha": SENHA})
    assert r.status_code == 200, r.text
    return ctx


BEARER = {"Authorization": f"Bearer {TOKEN}"}


async def deixar_online(fabrica, serial="agroedge-00001") -> None:
    async with fabrica() as s:
        disp = (
            await s.execute(select(Dispositivo).where(col(Dispositivo.serial) == serial))
        ).scalar_one()
        disp.status_mqtt = StatusMqtt.online
        disp.ultimo_contato = agora_utc()
        s.add(disp)
        await s.commit()


async def telemetria(fabrica, dados, serial="agroedge-00001") -> None:
    async with fabrica() as s:
        await processar_mensagem(
            s, f"agroedge/{serial}/telemetria", json.dumps(dados).encode(), agora_utc()
        )


# ---------------------------------------------------------------- autenticação


async def test_login_e_eu(logado):
    r = await logado["cliente"].get("/api/auth/eu")
    assert r.status_code == 200
    assert r.json()["email"] == "equipe@teste"


async def test_login_senha_errada(ctx):
    r = await ctx["cliente"].post("/api/auth/login", json={"email": "equipe@teste", "senha": "x"})
    assert r.status_code == 401
    assert r.json() == {"erro": "credenciais_invalidas", "mensagem": "E-mail ou senha incorretos."}


async def test_sem_sessao_nega_acesso(ctx):
    r = await ctx["cliente"].get("/api/fazendas")
    assert r.status_code == 401
    assert r.json()["erro"] == "nao_autenticado"


async def test_logout(logado):
    await logado["cliente"].post("/api/auth/logout")
    assert (await logado["cliente"].get("/api/auth/eu")).status_code == 401


async def test_token_valido(ctx):
    r = await ctx["cliente"].get("/api/fazendas", headers=BEARER)
    assert r.status_code == 200
    assert [f["nome"] for f in r.json()] == ["Fazenda"]


async def test_token_invalido(ctx):
    r = await ctx["cliente"].get("/api/fazendas", headers={"Authorization": "Bearer errado"})
    assert r.status_code == 401
    assert r.json()["erro"] == "token_invalido"


async def test_troca_de_senha(logado):
    c = logado["cliente"]
    r = await c.patch(
        "/api/auth/senha", json={"senha_atual": SENHA, "senha_nova": "nova-senha-123"}
    )
    assert r.status_code == 200
    await c.post("/api/auth/logout")
    r = await c.post("/api/auth/login", json={"email": "equipe@teste", "senha": "nova-senha-123"})
    assert r.status_code == 200


async def test_troca_de_senha_derruba_as_outras_sessoes(logado):
    outro = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")
    async with outro:
        r = await outro.post("/api/auth/login", json={"email": "equipe@teste", "senha": SENHA})
        assert r.status_code == 200
        r = await logado["cliente"].patch(
            "/api/auth/senha", json={"senha_atual": SENHA, "senha_nova": "nova-senha-123"}
        )
        assert r.status_code == 200
        assert (await outro.get("/api/auth/eu")).status_code == 401  # o outro navegador caiu
    assert (await logado["cliente"].get("/api/auth/eu")).status_code == 200  # quem trocou, não


async def test_login_bloqueia_depois_de_muitas_falhas(ctx):
    c = ctx["cliente"]
    errada = {"email": "equipe@teste", "senha": "chute"}
    for _ in range(limite_login.max_falhas):
        assert (await c.post("/api/auth/login", json=errada)).status_code == 401
    r = await c.post("/api/auth/login", json={"email": "equipe@teste", "senha": SENHA})
    assert r.status_code == 429  # nem a senha certa entra durante o bloqueio
    assert r.json()["erro"] == "muitas_tentativas"


async def test_login_certo_zera_as_falhas(ctx):
    c = ctx["cliente"]
    errada = {"email": "equipe@teste", "senha": "chute"}
    for _ in range(limite_login.max_falhas - 1):
        await c.post("/api/auth/login", json=errada)
    assert (
        await c.post("/api/auth/login", json={"email": "equipe@teste", "senha": SENHA})
    ).status_code == 200
    for _ in range(limite_login.max_falhas - 1):
        assert (await c.post("/api/auth/login", json=errada)).status_code == 401


async def test_login_de_email_inexistente_tambem_conta(ctx):
    c = ctx["cliente"]
    for _ in range(limite_login.max_falhas):
        await c.post("/api/auth/login", json={"email": "ninguem@teste", "senha": "x"})
    r = await c.post("/api/auth/login", json={"email": "equipe@teste", "senha": SENHA})
    assert r.status_code == 429  # o bloqueio é do IP


def test_limite_login_libera_depois_da_janela():
    agora = [1000.0]
    limite = LimiteLogin(max_falhas=2, janela_s=60, relogio=lambda: agora[0])
    chaves = [("ip:1", 2)]
    limite.falhou(["ip:1"])
    limite.falhou(["ip:1"])
    assert limite.espera_s(chaves) == 60
    agora[0] += 59
    assert limite.espera_s(chaves) == 1
    agora[0] += 1
    assert limite.espera_s(chaves) == 0


def test_producao_recusa_segredos_de_exemplo():
    s = Settings(
        _env_file=None,
        ambiente="producao",
        session_secret="gere-um-valor-aleatorio-longo",
        chatbot_token="curto",
        mqtt_senha="",
        mqtt_habilitado=True,  # o conftest desliga o MQTT nos testes
        admin_senha="troque-esta-senha",
    )
    problemas = " ".join(s.problemas_de_producao())
    for nome in ("SESSION_SECRET", "CHATBOT_TOKEN", "MQTT_SENHA", "ADMIN_SENHA"):
        assert nome in problemas
    assert "gere-um-valor" not in problemas  # nunca mostra o valor


def test_producao_aceita_segredos_fortes():
    s = Settings(
        _env_file=None,
        ambiente="producao",
        session_secret="a" * 43,
        chatbot_token="b" * 43,
        mqtt_senha="c" * 20,
        admin_senha="senha-forte-do-dono",
    )
    assert s.problemas_de_producao() == []
    assert s.docs_protegidos


async def test_docs_com_login_na_producao(ctx, monkeypatch):
    monkeypatch.setattr(settings_app, "docs_publicos", False)
    c = ctx["cliente"]
    assert (await c.get("/api/openapi.json")).status_code == 401
    assert (await c.get("/api/docs")).status_code == 401
    assert (await c.get("/api/openapi.json", headers=BEARER)).status_code == 200
    await c.post("/api/auth/login", json={"email": "equipe@teste", "senha": SENHA})
    assert (await c.get("/api/docs")).status_code == 200


# ---------------------------------------------------------------- posse


async def test_recursos_de_outro_usuario_dao_404(ctx):
    async with ctx["fabrica"]() as s:
        outro = Usuario(nome="Outro", email="outro@teste", senha_hash="x")
        s.add(outro)
        await s.flush()
        fazenda = Fazenda(usuario_id=outro.id, nome="Alheia")
        s.add(fazenda)
        await s.flush()
        cultivo = Cultivo(
            fazenda_id=fazenda.id, nome="Alheio", cultura="uva_italia",
            data_referencia=agora_utc().date(), area_m2=4, vazao_l_h=8,
        )  # fmt: skip
        s.add_all([cultivo, Dispositivo(serial="agroedge-09999", usuario_id=outro.id)])
        await s.commit()
        ids = (fazenda.id, cultivo.id)

    c = ctx["cliente"]
    for rota in (
        f"/api/cultivos/{ids[1]}",
        f"/api/cultivos/{ids[1]}/resumo",
        f"/api/fazendas/{ids[0]}/cultivos",
        "/api/dispositivos/agroedge-09999",
    ):
        r = await c.get(rota, headers=BEARER)
        assert r.status_code == 404, rota
        assert r.json()["erro"] == "nao_encontrado"
    # Nem usando um cultivo alheio como alvo da instalação
    r = await c.post(
        "/api/dispositivos/agroedge-00001/instalar", json={"cultivo_id": ids[1]}, headers=BEARER
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- fazendas e cultivos


async def test_crud_fazenda(logado):
    c = logado["cliente"]
    r = await c.post("/api/fazendas", json={"nome": "Vale Verde", "municipio": "Juazeiro - BA"})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert (await c.post("/api/fazendas", json={"nome": "vale verde"})).status_code == 409
    r = await c.patch(f"/api/fazendas/{fid}", json={"nome": "Vale Verde 2"})
    assert r.json()["nome"] == "Vale Verde 2"
    assert (await c.delete(f"/api/fazendas/{fid}")).status_code == 204
    # Fazenda com cultivos não pode ser excluída
    r = await c.delete(f"/api/fazendas/{logado['fazenda'].id}")
    assert r.status_code == 409


async def test_criar_cultivo_com_preset_de_solo(logado):
    c = logado["cliente"]
    r = await c.post(
        f"/api/fazendas/{logado['fazenda'].id}/cultivos",
        json={
            "nome": "Talhão 3", "cultura": "manga_tommy_atkins", "data_referencia": "2026-10-01",
            "textura_solo": "argiloso", "agua_disp": 0.07, "area_m2": 40, "vazao_l_h": 64,
        },
    )  # fmt: skip
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["agua_disp"] == 0.16  # preset do argiloso vence o valor digitado
    assert corpo["taw_mm"] == 96.0 and corpo["raw_mm"] == 48.0
    assert corpo["hora_irrigacao"] == "05:00"
    assert corpo["configuracao"] is None


async def test_cultivo_valores_fora_da_faixa(logado):
    r = await logado["cliente"].post(
        f"/api/fazendas/{logado['fazenda'].id}/cultivos",
        json={"nome": "X", "cultura": "uva_italia", "data_referencia": "2026-10-01",
              "eficiencia": 0.99, "area_m2": 4, "vazao_l_h": 8},
    )  # fmt: skip
    assert r.status_code == 422
    assert r.json()["erro"] == "dados_invalidos"


async def test_aviso_taw_fora_da_faixa(logado):
    r = await logado["cliente"].patch(
        f"/api/cultivos/{logado['uva'].id}",
        json={"textura_solo": "avancado", "agua_disp": 0.06, "raiz_m": 0.4},
    )
    assert r.status_code == 200
    assert r.json()["taw_mm"] == 24.0
    assert "fora da faixa" in r.json()["avisos"][0]


# ---------------------------------------------------------------- instalação e config (9.3, 9.4)


async def test_instalar_publica_config_e_placa_confirma(logado):
    c, pub = logado["cliente"], logado["pub"]
    r = await c.post(
        "/api/dispositivos/agroedge-00001/instalar", json={"cultivo_id": logado["manga"].id}
    )
    assert r.status_code == 201, r.text
    inst = r.json()
    assert inst["cfg_v"] == 1 and inst["config_publicada"]["cultura"] == "manga_tommy_atkins"
    serial, config = pub.configs[-1]
    assert serial == "agroedge-00001" and config["instalacao_id"] == inst["id"]
    assert config["hora_irrigacao"] == "05:00" and config["raiz_m"] is None

    cultivo = (await c.get(f"/api/cultivos/{logado['manga'].id}")).json()
    assert cultivo["configuracao"]["aplicada"] is False  # "aguardando a placa"

    await telemetria(logado["fabrica"], {"ts": datetime_para_ts(agora_utc()), "seq": 1, "cfg_v": 1})
    cultivo = (await c.get(f"/api/cultivos/{logado['manga'].id}")).json()
    assert cultivo["configuracao"]["aplicada"] is True


async def test_editar_cultivo_com_placa_gera_nova_versao(logado):
    c, pub = logado["cliente"], logado["pub"]
    await c.post(
        "/api/dispositivos/agroedge-00001/instalar", json={"cultivo_id": logado["manga"].id}
    )
    r = await c.patch(f"/api/cultivos/{logado['manga'].id}", json={"textura_solo": "arenoso"})
    assert r.json()["configuracao"]["cfg_v"] == 2
    assert pub.configs[-1][1]["agua_disp"] == 0.08 and pub.configs[-1][1]["cfg_v"] == 2

    # Mudar só o nome não gera nova versão
    n = len(pub.configs)
    r = await c.patch(f"/api/cultivos/{logado['manga'].id}", json={"nome": "Pomar renomeado"})
    assert r.json()["configuracao"]["cfg_v"] == 2 and len(pub.configs) == n

    # Nova poda/floração também gera nova versão
    r = await c.post(f"/api/cultivos/{logado['manga'].id}/poda", json={"data": "2026-11-01"})
    assert r.json()["configuracao"]["cfg_v"] == 3
    assert pub.configs[-1][1]["data_referencia"] == "2026-11-01"


async def test_editar_cultivo_sem_placa_so_salva(logado):
    r = await logado["cliente"].patch(f"/api/cultivos/{logado['uva'].id}", json={"eficiencia": 0.8})
    assert r.json()["eficiencia"] == 0.8
    assert logado["pub"].configs == []


async def test_config_com_broker_fora_fica_guardada(logado):
    logado["pub"].fora = True
    r = await logado["cliente"].post(
        "/api/dispositivos/agroedge-00001/instalar", json={"cultivo_id": logado["manga"].id}
    )
    assert r.status_code == 201
    assert r.json()["config_publicada"]["cfg_v"] == 1  # o ingestor republica ao reconectar


async def test_mudar_instalacao_com_inicio_no_passado_reatribui(logado):
    c, fabrica = logado["cliente"], logado["fabrica"]
    agora = agora_utc().replace(microsecond=0)
    r = await c.post(
        "/api/dispositivos/agroedge-00001/instalar",
        json={
            "cultivo_id": logado["uva"].id,
            "inicio": (agora - timedelta(days=2)).isoformat() + "Z",
        },
    )
    uva_id = r.json()["id"]
    agora_ts = datetime_para_ts(agora)
    await telemetria(
        fabrica, [{"ts": agora_ts - h * 3600, "seq": 10 - h} for h in range(6)]
    )  # leituras das últimas 5 h, todas na uva

    # A placa foi para a manga há 2 h (usuário informa depois)
    inicio_manga = agora - timedelta(hours=2)
    r = await c.post(
        "/api/dispositivos/agroedge-00001/instalar",
        json={"cultivo_id": logado["manga"].id, "inicio": inicio_manga.isoformat() + "Z"},
    )
    assert r.status_code == 201, r.text
    manga_id = r.json()["id"]
    async with fabrica() as s:
        leituras = (await s.execute(select(Leitura).order_by(col(Leitura.ts)))).scalars().all()
        assert [lt.instalacao_id for lt in leituras] == [uva_id] * 3 + [manga_id] * 3
        antiga = await s.get(Instalacao, uva_id)
        assert antiga.fim == inicio_manga

    # Início antes do início da instalação atual: sobreposição
    r = await c.post(
        "/api/dispositivos/agroedge-00001/instalar",
        json={
            "cultivo_id": logado["uva"].id,
            "inicio": (agora - timedelta(days=3)).isoformat() + "Z",
        },
    )
    assert r.status_code == 409 and r.json()["erro"] == "periodo_sobreposto"


async def test_cultivo_com_placa_nao_recebe_outra(logado):
    async with logado["fabrica"]() as s:
        s.add(Dispositivo(serial="agroedge-00002", usuario_id=logado["usuario"].id))
        await s.commit()
    c = logado["cliente"]
    await c.post(
        "/api/dispositivos/agroedge-00001/instalar", json={"cultivo_id": logado["manga"].id}
    )
    r = await c.post(
        "/api/dispositivos/agroedge-00002/instalar", json={"cultivo_id": logado["manga"].id}
    )
    assert r.status_code == 409 and r.json()["erro"] == "cultivo_ocupado"
    r = await c.post(f"/api/cultivos/{logado['manga'].id}/arquivar")
    assert r.status_code == 409


# ---------------------------------------------------------------- comandos (9.5)


async def test_comando_com_placa_offline_e_recusado(logado):
    r = await logado["cliente"].post(
        "/api/dispositivos/agroedge-00001/comandos", json={"acao": "abrir", "minutos": 10}
    )
    assert r.status_code == 409 and r.json()["erro"] == "dispositivo_offline"


async def test_comando_abrir_e_resposta(logado):
    c, pub, fabrica = logado["cliente"], logado["pub"], logado["fabrica"]
    await deixar_online(fabrica)
    r = await c.post(
        "/api/dispositivos/agroedge-00001/comandos",
        json={"acao": "abrir", "minutos": 10},
        headers=BEARER,
    )
    assert r.status_code == 201, r.text
    cmd = r.json()
    assert cmd["estado"] == "enviado"
    _, payload = pub.comandos[-1]
    assert payload["id"] == cmd["id"] and payload["minutos"] == 10
    assert payload["valido_ate"] - datetime_para_ts(agora_utc()) in range(590, 601)

    async with fabrica() as s:
        await processar_mensagem(
            s, "agroedge/agroedge-00001/cmd_resp",
            json.dumps({"id": cmd["id"], "ts": datetime_para_ts(agora_utc()), "resultado": "executado"}).encode(),
            agora_utc(),
        )  # fmt: skip
    lista = (await c.get("/api/dispositivos/agroedge-00001/comandos")).json()
    assert lista[0]["estado"] == "executado"


async def test_comando_minutos_invalidos(logado):
    await deixar_online(logado["fabrica"])
    r = await logado["cliente"].post(
        "/api/dispositivos/agroedge-00001/comandos", json={"acao": "abrir", "minutos": 500}
    )
    assert r.status_code == 400 and r.json()["erro"] == "minutos_invalidos"


async def test_comando_sem_broker(logado):
    await deixar_online(logado["fabrica"])
    logado["pub"].fora = True
    r = await logado["cliente"].post(
        "/api/dispositivos/agroedge-00001/comandos", json={"acao": "cancelar"}
    )
    assert r.status_code == 503
    assert (await logado["cliente"].get("/api/dispositivos/agroedge-00001/comandos")).json() == []


async def test_comando_vencido_expira(sessao, base):
    agora = agora_utc()
    sessao.add_all([
        Comando(id="velho", dispositivo_id=base["disp"].id, usuario_id=base["usuario"].id,
                acao="abrir", minutos=5, valido_ate=agora - timedelta(minutes=1)),
        Comando(id="novo", dispositivo_id=base["disp"].id, usuario_id=base["usuario"].id,
                acao="abrir", minutos=5, valido_ate=agora + timedelta(minutes=9)),
    ])  # fmt: skip
    await sessao.commit()
    eventos = await expirar_comandos(sessao, agora)
    assert [e.dados["id"] for e in eventos] == ["velho"]
    assert (await sessao.get(Comando, "velho")).estado == EstadoComando.expirado
    assert (await sessao.get(Comando, "novo")).estado == EstadoComando.enviado


# ---------------------------------------------------------------- dados


async def test_resumo(logado):
    c, fabrica = logado["cliente"], logado["fabrica"]
    await c.post("/api/dispositivos/agroedge-00001/instalar", json={
        "cultivo_id": logado["manga"].id,
        "inicio": (agora_utc() - timedelta(days=3)).isoformat() + "Z",
    })  # fmt: skip
    await deixar_online(fabrica)
    agora_ts = datetime_para_ts(agora_utc())
    await telemetria(
        fabrica, {"ts": agora_ts - 60, "seq": 5, "temp_c": 31.4, "rssi": -60, "buf": 0, "cfg_v": 1}
    )
    async with fabrica() as s:
        diario = {"ts": agora_ts - 3600, "seq": 1, "data": (agora_utc() - timedelta(days=1)).date().isoformat(),
                  "fase": "queda_frutos", "classe": 1, "lamina_bruta": 6.1, "minutos": 107.1,
                  "chuva": 0.0, "irrigacao": 5.6, "etc": 3.38, "et0": 5.2, "avisos": []}  # fmt: skip
        await processar_mensagem(
            s, "agroedge/agroedge-00001/diario", json.dumps(diario).encode(), agora_utc()
        )

    r = await c.get(f"/api/cultivos/{logado['manga'].id}/resumo", headers=BEARER)
    assert r.status_code == 200, r.text
    resumo = r.json()
    assert resumo["dispositivo"]["status"] == "ao_vivo"
    assert resumo["dispositivo"]["cfg_aplicada"] is True
    assert resumo["ultima_leitura"]["temp_c"] == 31.4
    assert resumo["ultimo_diario"]["lamina_bruta"] == 6.1
    assert resumo["ciclo"]["fase_nome"] == "Queda de frutos"
    assert resumo["cultivo"]["fazenda"]["nome"] == "Fazenda"
    assert resumo["valvula"]["proxima_prevista"].endswith("Z")
    assert len(resumo["ultimos_7_dias"]) == 7 and resumo["ultimos_7_dias"][-1]["hoje"]


async def test_series_com_lacuna_e_agregacao(logado):
    c, fabrica = logado["cliente"], logado["fabrica"]
    agora = agora_utc().replace(minute=0, second=0, microsecond=0)
    await c.post("/api/dispositivos/agroedge-00001/instalar", json={
        "cultivo_id": logado["manga"].id, "inicio": (agora - timedelta(days=1)).isoformat() + "Z",
    })  # fmt: skip
    base_ts = datetime_para_ts(agora) - 6 * 3600
    # 2 h de leituras, 2 h sem contato, mais 1 h
    tss = [base_ts + i * 900 for i in range(8)] + [base_ts + 4 * 3600 + i * 900 for i in range(4)]
    await telemetria(
        fabrica, [{"ts": t, "seq": n, "temp_c": 30.0, "chuva_mm": 0.5} for n, t in enumerate(tss)]
    )

    url = f"/api/cultivos/{logado['manga'].id}/leituras"
    r = (await c.get(url, params={"variaveis": "temp_c,chuva_mm"})).json()
    assert r["resolucao"] == "bruta" and len(r["pontos"]) == 12
    assert r["lacunas"] == [{"inicio": tss[7], "fim": tss[8]}]

    r = (await c.get(url, params={"variaveis": "temp_c,chuva_mm", "resolucao": "hora"})).json()
    assert len(r["pontos"]) == 3
    assert r["pontos"][0]["chuva_mm"] == 2.0 and r["pontos"][0]["temp_c"] == 30.0

    r = await c.get(url, params={"variaveis": "senha"})
    assert r.status_code == 400


async def test_exportar_csv(logado):
    c, fabrica = logado["cliente"], logado["fabrica"]
    await c.post("/api/dispositivos/agroedge-00001/instalar", json={
        "cultivo_id": logado["manga"].id, "inicio": (agora_utc() - timedelta(days=1)).isoformat() + "Z",
    })  # fmt: skip
    await telemetria(fabrica, {"ts": datetime_para_ts(agora_utc()) - 60, "seq": 1, "temp_c": 31.45})
    r = await c.get(f"/api/cultivos/{logado['manga'].id}/exportar.csv", params={"tipo": "leituras"})
    assert r.status_code == 200
    assert r.content.startswith("﻿".encode())
    linhas = r.content.decode("utf-8-sig").splitlines()
    assert linhas[0].startswith("Data e hora;Temperatura (°C);")
    assert ";31,45;" in linhas[1]


async def test_openapi_documentado(ctx):
    r = await ctx["cliente"].get("/api/openapi.json")
    caminhos = r.json()["paths"]
    for rota in (
        "/api/cultivos/{cultivo_id}/resumo",
        "/api/dispositivos/{serial}/comandos",
        "/api/stream",
    ):
        assert rota in caminhos


async def test_exportar_csv_com_rotulos_em_portugues(logado):
    c, fabrica = logado["cliente"], logado["fabrica"]
    await c.post("/api/dispositivos/agroedge-00001/instalar", json={
        "cultivo_id": logado["manga"].id, "inicio": (agora_utc() - timedelta(days=1)).isoformat() + "Z",
    })  # fmt: skip
    ts = datetime_para_ts(agora_utc()) - 3600
    async with fabrica() as s:
        await processar_mensagem(
            s, "agroedge/agroedge-00001/irrigacao",
            json.dumps({"id": "x-auto", "ts_inicio": ts, "ts_fim": ts + 600, "minutos": 10.0,
                        "mm": 2.5, "origem": "automatica", "estado": "concluida"}).encode(),
            agora_utc(),
        )  # fmt: skip
    r = await c.get(
        f"/api/cultivos/{logado['manga'].id}/exportar.csv", params={"tipo": "irrigacoes"}
    )
    linhas = r.content.decode("utf-8-sig").splitlines()
    assert linhas[0] == "Início;Fim;Minutos;Lâmina (mm);Origem;Estado"
    assert linhas[1].endswith(";10;2,5;Automática;Concluída")


async def test_exportar_csv_de_fechamentos(logado):
    c, fabrica = logado["cliente"], logado["fabrica"]
    await c.post("/api/dispositivos/agroedge-00001/instalar", json={
        "cultivo_id": logado["manga"].id, "inicio": (agora_utc() - timedelta(days=3)).isoformat() + "Z",
    })  # fmt: skip
    ontem = (agora_utc() - timedelta(days=1)).date()
    async with fabrica() as s:
        diario = {"ts": datetime_para_ts(agora_utc()) - 600, "seq": 1, "data": ontem.isoformat(),
                  "classe": 2, "et0": 5.2, "lamina_bruta": 20.4, "avisos": ["a", "b"]}  # fmt: skip
        await processar_mensagem(
            s, "agroedge/agroedge-00001/diario", json.dumps(diario).encode(), agora_utc()
        )
    r = await c.get(f"/api/cultivos/{logado['manga'].id}/exportar.csv", params={"tipo": "diarios"})
    assert r.status_code == 200, r.text
    linhas = r.content.decode("utf-8-sig").splitlines()
    assert linhas[0].startswith("Data;Dias após a referência;Fase;Kc;")
    assert ";Déficit crítico;20,4;" in linhas[1] and linhas[1].endswith(";a | b")


async def test_stream_envia_algo_logo_ao_conectar(base):
    """Sem um primeiro envio imediato, proxies seguram os cabeçalhos e o navegador não abre.

    (O cliente de testes do httpx espera a resposta terminar, e um SSE não termina; por isso
    o teste lê direto o primeiro item do gerador da rota.)"""
    from starlette.requests import Request

    from app.rotas.stream import stream

    pedido = Request({"type": "http", "method": "GET", "path": "/api/stream", "headers": []})
    resposta = await stream(pedido, base["usuario"])
    primeiro = await anext(resposta.body_iterator)
    texto = primeiro.encode().decode() if hasattr(primeiro, "encode") else str(primeiro)
    assert ": conectado" in texto and "retry: 3000" in texto
    await resposta.body_iterator.aclose()


async def test_stream_sem_token_nega(ctx):
    r = await ctx["cliente"].get("/api/stream")
    assert r.status_code == 401


async def test_editar_intervalo_publica_nova_config(logado):
    c, pub = logado["cliente"], logado["pub"]
    # Sem instalação: só salva, não publica
    r = await c.patch(
        "/api/dispositivos/agroedge-00001",
        json={"intervalo_telemetria_min": 5, "apelido": " Bancada "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["intervalo_telemetria_min"] == 5 and r.json()["apelido"] == "Bancada"
    assert pub.configs == []
    # Com instalação: nova versão da config, com o intervalo novo
    await c.post(
        "/api/dispositivos/agroedge-00001/instalar", json={"cultivo_id": logado["manga"].id}
    )
    r = await c.patch("/api/dispositivos/agroedge-00001", json={"intervalo_telemetria_min": 10})
    assert r.json()["instalacao"]["cfg_v"] == 2
    assert pub.configs[-1][1]["intervalo_telemetria_min"] == 10 and pub.configs[-1][1]["cfg_v"] == 2
    # Mesmo valor: nada muda
    n = len(pub.configs)
    await c.patch("/api/dispositivos/agroedge-00001", json={"intervalo_telemetria_min": 10})
    assert len(pub.configs) == n
    # Fora da faixa
    r = await c.patch("/api/dispositivos/agroedge-00001", json={"intervalo_telemetria_min": 0})
    assert r.status_code == 422
