"""Ingestão das mensagens MQTT da placa (regras 9.1 e 9.2). Sem FastAPI aqui.

`processar_mensagem` recebe tópico e payload crus, grava o que for válido e devolve os
eventos para o barramento. Quem chama (o ingestor) decide o que fazer com eles.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.eventos import Evento
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
    agora_utc,
    ts_para_datetime,
)
from app.schemas.mqtt import CmdRespPayload, DiarioPayload, IrrigacaoPayload, TelemetriaPayload
from app.servicos.sql import inserir_ignorando, upsert

log = logging.getLogger("ingestao")

TS_MINIMO = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())
JANELA_FUTURO_S = 24 * 3600
LOTE_MAXIMO = 50
PAYLOAD_MAXIMO_REJEITADA = 4096
QUEDA_SEQ_REINICIO = 1000  # queda de seq maior que isso = placa reiniciou o contador

TIPOS = ("telemetria", "diario", "irrigacao", "cmd_resp", "status")


class Rejeitada(Exception):
    """Mensagem (ou parte dela) descartada; vai para mensagens_rejeitadas."""


# ---------------------------------------------------------------- auxiliares


async def registrar_rejeitada(
    sessao: AsyncSession, topico: str, payload: bytes | str, motivo: str
) -> None:
    texto = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    sessao.add(
        MensagemRejeitada(topico=topico, payload=texto[:PAYLOAD_MAXIMO_REJEITADA], motivo=motivo)
    )
    log.warning("ingestao rejeitada topico=%s motivo=%s", topico, motivo)


def ts_valido(ts: int, agora: datetime) -> bool:
    agora_ts = int(agora.replace(tzinfo=UTC).timestamp())
    return TS_MINIMO <= ts <= agora_ts + JANELA_FUTURO_S


def separar_topico(topico: str) -> tuple[str, str] | None:
    """`agroedge/{serial}/{tipo}` → (serial, tipo)."""
    partes = topico.split("/")
    if len(partes) != 3 or partes[0] != "agroedge" or partes[2] not in TIPOS:
        return None
    return partes[1], partes[2]


async def instalacoes_do_dispositivo(
    sessao: AsyncSession, dispositivo_id: int | None
) -> list[Instalacao]:
    resultado = await sessao.execute(
        select(Instalacao)
        .where(col(Instalacao.dispositivo_id) == dispositivo_id)
        .order_by(col(Instalacao.inicio))
    )
    return list(resultado.scalars())


def instalacao_por_ts(instalacoes: list[Instalacao], ts: int) -> Instalacao | None:
    """Regra 9.2: a instalação cujo período contém o ts (inicio ≤ ts < fim, ou fim nulo)."""
    momento = ts_para_datetime(ts)
    for inst in instalacoes:
        if inst.inicio <= momento and (inst.fim is None or momento < inst.fim):
            return inst
    return None


def _conferir_instalacao_informada(serial: str, informada: int | None, inst: Instalacao | None):
    calculada = inst.id if inst else None
    if informada is not None and informada != calculada:
        log.info(
            "ingestao instalacao divergente serial=%s placa=%s calculada=%s",
            serial,
            informada,
            calculada,
        )


def _validar(modelo: type[BaseModel], dados: Any) -> Any:
    try:
        return modelo.model_validate(dados)
    except ValidationError as erro:
        campos = ", ".join(".".join(str(p) for p in e["loc"]) or "?" for e in erro.errors())
        raise Rejeitada(f"payload inválido ({campos})") from erro


# ---------------------------------------------------------------- entrada


async def processar_mensagem(
    sessao: AsyncSession, topico: str, payload: bytes, agora: datetime | None = None
) -> list[Evento]:
    """Processa uma mensagem MQTT e faz commit. Devolve os eventos gerados."""
    agora = agora or agora_utc()
    partes = separar_topico(topico)
    if partes is None:
        await registrar_rejeitada(sessao, topico, payload, "tópico desconhecido")
        await sessao.commit()
        return []
    serial, tipo = partes

    dispositivo = (
        await sessao.execute(select(Dispositivo).where(col(Dispositivo.serial) == serial))
    ).scalar_one_or_none()
    if dispositivo is None:
        await registrar_rejeitada(sessao, topico, payload, f"serial não cadastrado: {serial}")
        await sessao.commit()
        return []

    try:
        if tipo == "status":
            eventos = await _status(sessao, dispositivo, payload)
        else:
            try:
                dados = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as erro:
                raise Rejeitada("JSON inválido") from erro
            tratador = {
                "telemetria": _telemetria,
                "diario": _diario,
                "irrigacao": _irrigacao,
                "cmd_resp": _cmd_resp,
            }[tipo]
            eventos = await tratador(sessao, dispositivo, dados, topico, agora)
    except Rejeitada as erro:
        await sessao.rollback()
        await registrar_rejeitada(sessao, topico, payload, str(erro))
        await sessao.commit()
        return []

    # Regra 9.1.2: qualquer mensagem válida conta como contato. Exceto o "offline" do LWT:
    # quem publica é o broker, quando a placa já sumiu (senão a pill diria "sem contato
    # desde" a hora em que o broker percebeu a queda, não a do último contato real).
    if not (tipo == "status" and dispositivo.status_mqtt == StatusMqtt.offline):
        dispositivo.ultimo_contato = agora
    sessao.add(dispositivo)
    await sessao.commit()
    return eventos


# ---------------------------------------------------------------- por tipo


async def _status(sessao: AsyncSession, dispositivo: Dispositivo, payload: bytes) -> list[Evento]:
    texto = payload.decode("utf-8", "replace").strip().lower()
    if texto not in ("online", "offline"):
        raise Rejeitada(f"status inválido: {texto[:30]!r}")
    dispositivo.status_mqtt = StatusMqtt(texto)
    log.info("ingestao status serial=%s status=%s", dispositivo.serial, texto)
    ativa = next(
        (i for i in await instalacoes_do_dispositivo(sessao, dispositivo.id) if i.fim is None),
        None,
    )
    return [
        Evento(
            "status",
            dispositivo.serial,
            ativa.cultivo_id if ativa else None,
            {"status": texto},
        )
    ]


async def _telemetria(
    sessao: AsyncSession, dispositivo: Dispositivo, dados: Any, topico: str, agora: datetime
) -> list[Evento]:
    itens = dados if isinstance(dados, list) else [dados]
    if not itens:
        raise Rejeitada("lote vazio")
    if len(itens) > LOTE_MAXIMO:
        raise Rejeitada(f"lote com {len(itens)} leituras (máximo {LOTE_MAXIMO})")
    # Valida o lote inteiro antes de gravar: campo obrigatório ausente descarta a mensagem.
    leituras = [_validar(TelemetriaPayload, item) for item in itens]

    instalacoes = await instalacoes_do_dispositivo(sessao, dispositivo.id)
    inseridas = duplicadas = invalidas = 0
    por_cultivo: dict[int | None, int] = {}
    configs_aplicadas: list[Instalacao] = []
    buf_atual: int | None = None

    for leitura, bruto in zip(leituras, itens, strict=True):
        if not ts_valido(leitura.ts, agora):
            invalidas += 1
            await registrar_rejeitada(
                sessao, topico, json.dumps(bruto), f"ts fora da janela: {leitura.ts}"
            )
            continue
        inst = instalacao_por_ts(instalacoes, leitura.ts)
        _conferir_instalacao_informada(dispositivo.serial, leitura.instalacao_id, inst)
        valores = leitura.model_dump(exclude={"instalacao_id"})
        valores.update(
            dispositivo_id=dispositivo.id,
            instalacao_id=inst.id if inst else None,
            recebido_em=agora,
        )
        if await inserir_ignorando(sessao, Leitura, valores, ["dispositivo_id", "ts"]):
            inseridas += 1
            chave = inst.cultivo_id if inst else None
            por_cultivo[chave] = por_cultivo.get(chave, 0) + 1
        else:
            duplicadas += 1
        _acompanhar_seq(dispositivo, leitura)
        if buf_atual is None:
            buf_atual = leitura.buf
        # Regra 9.1.6. A confirmação vale para a instalação que a placa diz ter configurada
        # (se informou); senão, para a do período. Assim uma leitura antiga do buffer, com
        # cfg_v de outra instalação, não confirma a errada.
        alvo = (
            next((i for i in instalacoes if i.id == leitura.instalacao_id), None)
            if leitura.instalacao_id is not None
            else inst
        )
        if (
            alvo is not None
            and leitura.cfg_v is not None
            and leitura.cfg_v == alvo.cfg_v
            and alvo.cfg_v_aplicada != alvo.cfg_v
        ):
            alvo.cfg_v_aplicada = alvo.cfg_v
            sessao.add(alvo)
            configs_aplicadas.append(alvo)

    log.info(
        "ingestao telemetria serial=%s n=%d inseridas=%d duplicadas=%d invalidas=%d",
        dispositivo.serial,
        len(leituras),
        inseridas,
        duplicadas,
        invalidas,
    )
    eventos = [
        Evento("leitura", dispositivo.serial, cultivo_id, {"n": n, "buf": buf_atual})
        for cultivo_id, n in por_cultivo.items()
    ]
    eventos += [
        Evento(
            "config_aplicada",
            dispositivo.serial,
            inst.cultivo_id,
            {"instalacao_id": inst.id, "cfg_v": inst.cfg_v},
        )
        for inst in configs_aplicadas
    ]
    return eventos


def _acompanhar_seq(dispositivo: Dispositivo, leitura: TelemetriaPayload) -> None:
    """Regra 9.1.5: detecta perdas pelo `seq`; reinício do contador é só aceito."""
    anterior = dispositivo.ultimo_seq
    if anterior is None or leitura.seq > anterior:
        if anterior is not None and leitura.seq > anterior + 1 and not leitura.buf:
            log.warning(
                "ingestao seq perdidas serial=%s de=%d ate=%d perdidas=%d",
                dispositivo.serial,
                anterior,
                leitura.seq,
                leitura.seq - anterior - 1,
            )
        dispositivo.ultimo_seq = leitura.seq
    elif leitura.seq < anterior - QUEDA_SEQ_REINICIO:
        log.info("ingestao seq reiniciado serial=%s seq=%d", dispositivo.serial, leitura.seq)
        dispositivo.ultimo_seq = leitura.seq
    # seq menor que o último, sem queda grande: leitura atrasada vinda do buffer.


async def _diario(
    sessao: AsyncSession, dispositivo: Dispositivo, dados: Any, topico: str, agora: datetime
) -> list[Evento]:
    diario = _validar(DiarioPayload, dados)
    if not ts_valido(diario.ts, agora):
        raise Rejeitada(f"ts fora da janela: {diario.ts}")
    inst = instalacao_por_ts(await instalacoes_do_dispositivo(sessao, dispositivo.id), diario.ts)
    _conferir_instalacao_informada(dispositivo.serial, diario.instalacao_id, inst)
    valores = diario.model_dump(exclude={"instalacao_id"})
    valores.update(
        dispositivo_id=dispositivo.id, instalacao_id=inst.id if inst else None, recebido_em=agora
    )
    await upsert(sessao, Diario, valores, ["dispositivo_id", "data"])
    log.info(
        "ingestao diario serial=%s data=%s classe=%s lamina=%s",
        dispositivo.serial,
        diario.data,
        diario.classe,
        diario.lamina_bruta,
    )
    return [
        Evento(
            "diario",
            dispositivo.serial,
            inst.cultivo_id if inst else None,
            {
                "data": diario.data.isoformat(),
                "lamina_bruta": diario.lamina_bruta,
                "minutos": diario.minutos,
                "classe": diario.classe,
            },
        )
    ]


async def _irrigacao(
    sessao: AsyncSession, dispositivo: Dispositivo, dados: Any, topico: str, agora: datetime
) -> list[Evento]:
    irr = _validar(IrrigacaoPayload, dados)
    if not ts_valido(irr.ts_inicio, agora):
        raise Rejeitada(f"ts_inicio fora da janela: {irr.ts_inicio}")
    existente = await sessao.get(Irrigacao, irr.id)
    if existente is not None and existente.dispositivo_id != dispositivo.id:
        raise Rejeitada(f"irrigação {irr.id} pertence a outro dispositivo")
    inst = instalacao_por_ts(
        await instalacoes_do_dispositivo(sessao, dispositivo.id), irr.ts_inicio
    )
    valores = irr.model_dump()
    valores.update(
        dispositivo_id=dispositivo.id, instalacao_id=inst.id if inst else None, atualizado_em=agora
    )
    await upsert(sessao, Irrigacao, valores, ["id"])
    log.info(
        "ingestao irrigacao serial=%s id=%s estado=%s minutos=%s",
        dispositivo.serial,
        irr.id,
        irr.estado,
        irr.minutos,
    )
    return [
        Evento(
            "irrigacao",
            dispositivo.serial,
            inst.cultivo_id if inst else None,
            {"id": irr.id, "estado": irr.estado, "origem": irr.origem, "minutos": irr.minutos},
        )
    ]


async def _cmd_resp(
    sessao: AsyncSession, dispositivo: Dispositivo, dados: Any, topico: str, agora: datetime
) -> list[Evento]:
    resp = _validar(CmdRespPayload, dados)
    comando = await sessao.get(Comando, resp.id)
    if comando is None or comando.dispositivo_id != dispositivo.id:
        raise Rejeitada(f"comando desconhecido: {resp.id}")
    if resp.resultado == "executado":
        comando.estado = EstadoComando.executado  # a verdade da placa vale, mesmo se tardia
    elif comando.estado != EstadoComando.expirado:
        comando.estado = EstadoComando.recusado
    # Resposta tardia a um comando já expirado (placa voltou e recusou o vencido): continua
    # "expirado", só registra o que a placa disse.
    comando.resultado = resp.resultado
    comando.respondido_em = agora
    sessao.add(comando)
    log.info(
        "ingestao cmd_resp serial=%s id=%s resultado=%s",
        dispositivo.serial,
        resp.id,
        resp.resultado,
    )
    ativa = next(
        (i for i in await instalacoes_do_dispositivo(sessao, dispositivo.id) if i.fim is None),
        None,
    )
    return [
        Evento(
            "comando",
            dispositivo.serial,
            ativa.cultivo_id if ativa else None,
            {"id": comando.id, "estado": comando.estado.value, "resultado": resp.resultado},
        )
    ]
