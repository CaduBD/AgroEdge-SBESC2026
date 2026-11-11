"""Testes da ingestão MQTT (regras 9.1 e 9.2)."""

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Comando,
    Diario,
    Dispositivo,
    EstadoComando,
    Instalacao,
    Irrigacao,
    Leitura,
    MensagemRejeitada,
    StatusMqtt,
    datetime_para_ts,
)
from app.servicos.ingestao import processar_mensagem
from tests.conftest import AGORA

TS = datetime_para_ts(AGORA) - 3600  # 11:00 UTC


def leitura(ts: int = TS, seq: int = 1, **extra) -> dict:
    return {"ts": ts, "seq": seq, "temp_c": 31.4, "ur_pct": 38.2, "buf": 0, **extra}


async def enviar(sessao: AsyncSession, tipo: str, dados, serial: str = "agroedge-00001"):
    payload = dados if isinstance(dados, bytes) else json.dumps(dados).encode()
    return await processar_mensagem(sessao, f"agroedge/{serial}/{tipo}", payload, AGORA)


async def contar(sessao: AsyncSession, modelo) -> int:
    return (await sessao.execute(select(func.count()).select_from(modelo))).scalar_one()


async def instalar(sessao, base, cultivo, inicio: datetime, fim: datetime | None = None, cfg_v=1):
    inst = Instalacao(
        dispositivo_id=base["disp"].id, cultivo_id=cultivo.id, inicio=inicio, fim=fim, cfg_v=cfg_v
    )
    sessao.add(inst)
    await sessao.commit()
    return inst


# ---------------------------------------------------------------- telemetria


async def test_telemetria_grava_e_atualiza_contato(sessao, base):
    eventos = await enviar(sessao, "telemetria", leitura())
    assert await contar(sessao, Leitura) == 1
    disp = await sessao.get(Dispositivo, base["disp"].id)
    assert disp.ultimo_contato == AGORA
    assert disp.ultimo_seq == 1
    assert [e.tipo for e in eventos] == ["leitura"]


async def test_mensagem_repetida_nao_duplica(sessao, base):
    await enviar(sessao, "telemetria", leitura())
    await enviar(sessao, "telemetria", leitura())
    assert await contar(sessao, Leitura) == 1


async def test_lote_de_leituras(sessao, base):
    lote = [leitura(TS - 900 * i, seq=100 - i) for i in range(10)]
    await enviar(sessao, "telemetria", lote)
    assert await contar(sessao, Leitura) == 10


async def test_lote_acima_do_limite_rejeitado(sessao, base):
    lote = [leitura(TS - 900 * i, seq=100 - i) for i in range(51)]
    await enviar(sessao, "telemetria", lote)
    assert await contar(sessao, Leitura) == 0
    assert await contar(sessao, MensagemRejeitada) == 1


async def test_campo_obrigatorio_ausente_descarta_lote_inteiro(sessao, base):
    await enviar(sessao, "telemetria", [leitura(), {"ts": TS - 900}])  # 2ª sem seq
    assert await contar(sessao, Leitura) == 0
    assert await contar(sessao, MensagemRejeitada) == 1


async def test_ts_invalido_rejeita_so_a_leitura(sessao, base):
    antigo = datetime_para_ts(datetime(2023, 12, 31))
    futuro = datetime_para_ts(AGORA + timedelta(hours=25))
    await enviar(sessao, "telemetria", [leitura(), leitura(antigo, 2), leitura(futuro, 3)])
    assert await contar(sessao, Leitura) == 1
    assert await contar(sessao, MensagemRejeitada) == 2


async def test_campos_desconhecidos_sao_ignorados(sessao, base):
    await enviar(sessao, "telemetria", leitura(campo_novo=123))
    assert await contar(sessao, Leitura) == 1


async def test_json_invalido(sessao, base):
    await enviar(sessao, "telemetria", b"{nao e json")
    assert await contar(sessao, MensagemRejeitada) == 1


async def test_serial_desconhecido_vai_para_rejeitadas(sessao, base):
    await enviar(sessao, "telemetria", leitura(), serial="agroedge-99999")
    assert await contar(sessao, Leitura) == 0
    rejeitada = (await sessao.execute(select(MensagemRejeitada))).scalar_one()
    assert "agroedge-99999" in rejeitada.motivo


# ---------------------------------------------------------------- atribuição (9.2)


async def test_atribuicao_por_periodo(sessao, base):
    """Leituras do buffer vão para a instalação do momento em que foram medidas."""
    troca = AGORA - timedelta(hours=6)
    antiga = await instalar(sessao, base, base["uva"], AGORA - timedelta(days=10), fim=troca)
    nova = await instalar(sessao, base, base["manga"], troca)
    ts_troca = datetime_para_ts(troca)

    # Lote chegando agora, com leituras de antes e depois da troca.
    await enviar(
        sessao,
        "telemetria",
        [leitura(ts_troca - 900, 1), leitura(ts_troca, 2), leitura(ts_troca + 900, 3)],
    )
    leituras = (await sessao.execute(select(Leitura).order_by(Leitura.ts))).scalars().all()
    assert [lt.instalacao_id for lt in leituras] == [antiga.id, nova.id, nova.id]


async def test_sem_instalacao_grava_com_instalacao_nula(sessao, base):
    await enviar(sessao, "telemetria", leitura())
    lt = (await sessao.execute(select(Leitura))).scalar_one()
    assert lt.instalacao_id is None


async def test_cfg_v_aplicada(sessao, base):
    inst = await instalar(sessao, base, base["manga"], AGORA - timedelta(days=1), cfg_v=5)
    eventos = await enviar(sessao, "telemetria", leitura(cfg_v=4))
    await sessao.refresh(inst)
    assert inst.cfg_v_aplicada is None
    assert "config_aplicada" not in [e.tipo for e in eventos]

    eventos = await enviar(sessao, "telemetria", leitura(TS + 900, 2, cfg_v=5))
    await sessao.refresh(inst)
    assert inst.cfg_v_aplicada == 5
    assert "config_aplicada" in [e.tipo for e in eventos]


async def test_cfg_v_vale_para_a_instalacao_informada_pela_placa(sessao, base):
    """Leitura antiga (período da instalação A) enviada depois que a placa já tem a config
    da B: a confirmação é da B, que é o que a placa diz ter."""
    troca = AGORA - timedelta(hours=1)
    a = await instalar(sessao, base, base["uva"], AGORA - timedelta(days=1), fim=troca)
    b = await instalar(sessao, base, base["manga"], troca)
    await enviar(sessao, "telemetria", leitura(TS - 7200, 1, cfg_v=1, instalacao_id=b.id))
    await sessao.refresh(a)
    await sessao.refresh(b)
    assert a.cfg_v_aplicada is None
    assert b.cfg_v_aplicada == 1


# ---------------------------------------------------------------- diário, irrigação, cmd, status


def diario(data: str = "2026-11-09", lamina: float = 20.4) -> dict:
    return {
        "ts": TS,
        "seq": 87,
        "data": data,
        "cultura": "manga_tommy_atkins",
        "dap": 42,
        "fase": "queda_frutos",
        "kc": 0.65,
        "classe": 1,
        "lamina_bruta": lamina,
        "minutos": 107.1,
        "avisos": ["histórico com 12 dias"],
    }


async def test_diario_reenviado_atualiza(sessao, base):
    inst = await instalar(sessao, base, base["manga"], AGORA - timedelta(days=1))
    eventos = await enviar(sessao, "diario", diario())
    await enviar(sessao, "diario", diario(lamina=18.0))
    registros = (await sessao.execute(select(Diario))).scalars().all()
    assert len(registros) == 1
    assert registros[0].lamina_bruta == 18.0
    assert registros[0].instalacao_id == inst.id
    assert registros[0].avisos == ["histórico com 12 dias"]
    assert eventos[0].tipo == "diario" and eventos[0].cultivo_id == base["manga"].id


async def test_diario_classe_invalida(sessao, base):
    await enviar(sessao, "diario", {**diario(), "classe": 3})
    assert await contar(sessao, Diario) == 0
    assert await contar(sessao, MensagemRejeitada) == 1


async def test_irrigacao_upsert_pelo_id(sessao, base):
    inicio = {
        "id": "1762490000-auto",
        "ts_inicio": TS,
        "origem": "automatica",
        "estado": "iniciada",
    }
    await enviar(sessao, "irrigacao", inicio)
    await enviar(
        sessao,
        "irrigacao",
        {**inicio, "ts_fim": TS + 6426, "minutos": 107.1, "mm": 20.4, "estado": "concluida"},
    )
    irr = (await sessao.execute(select(Irrigacao))).scalar_one()
    assert irr.estado == "concluida"
    assert irr.minutos == 107.1


async def test_cmd_resp_atualiza_comando(sessao, base):
    cmd = Comando(
        id="cmd-1",
        dispositivo_id=base["disp"].id,
        usuario_id=base["usuario"].id,
        acao="abrir",
        minutos=10,
        valido_ate=AGORA + timedelta(minutes=10),
    )
    sessao.add(cmd)
    await sessao.commit()
    await enviar(sessao, "cmd_resp", {"id": "cmd-1", "ts": TS, "resultado": "recusado_vencido"})
    await sessao.refresh(cmd)
    assert cmd.estado == EstadoComando.recusado
    assert cmd.resultado == "recusado_vencido"


async def test_resposta_tardia_mantem_expirado(sessao, base):
    cmd = Comando(
        id="cmd-velho", dispositivo_id=base["disp"].id, usuario_id=base["usuario"].id,
        acao="abrir", minutos=5, valido_ate=AGORA - timedelta(minutes=1),
        estado=EstadoComando.expirado,
    )  # fmt: skip
    sessao.add(cmd)
    await sessao.commit()
    await enviar(sessao, "cmd_resp", {"id": "cmd-velho", "ts": TS, "resultado": "recusado_vencido"})
    await sessao.refresh(cmd)
    assert cmd.estado == EstadoComando.expirado
    assert cmd.resultado == "recusado_vencido"


async def test_cmd_resp_de_comando_desconhecido(sessao, base):
    await enviar(sessao, "cmd_resp", {"id": "nao-existe", "ts": TS, "resultado": "executado"})
    assert await contar(sessao, MensagemRejeitada) == 1


async def test_offline_do_lwt_nao_conta_como_contato(sessao, base):
    """O "offline" é publicado pelo broker quando a placa some: não é contato da placa."""
    await enviar(sessao, "status", b"online")
    disp = await sessao.get(Dispositivo, base["disp"].id)
    contato = disp.ultimo_contato
    await processar_mensagem(
        sessao, "agroedge/agroedge-00001/status", b"offline", AGORA + timedelta(minutes=2)
    )
    await sessao.refresh(disp)
    assert disp.status_mqtt == StatusMqtt.offline
    assert disp.ultimo_contato == contato


async def test_status(sessao, base):
    await enviar(sessao, "status", b"online")
    disp = await sessao.get(Dispositivo, base["disp"].id)
    assert disp.status_mqtt == StatusMqtt.online
    await enviar(sessao, "status", b"offline")
    await sessao.refresh(disp)
    assert disp.status_mqtt == StatusMqtt.offline
