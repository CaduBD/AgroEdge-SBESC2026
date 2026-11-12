"""Textos para o produtor, em pt-BR, a partir das respostas da API.

Regras (CHATBOT.md): o bot só repassa o que a placa calculou (não recalcula nada);
horários vêm em UTC e aparecem no fuso local; números com vírgula decimal.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from agroedge_bot.nucleo.mensagens import esc

# ---------------------------------------------------------------- rótulos (iguais ao painel)

CLASSE = {
    0: ("🟢", "Adequado"),
    1: ("🟡", "Déficit moderado"),
    2: ("🔴", "Déficit crítico"),
}
SEM_CLASSE = ("⚪", "Sem classe")

STATUS_PLACA = {
    "ao_vivo": "ao vivo",
    "atrasado": "atrasada",
    "sincronizando": "sincronizando",
    "sem_contato": "sem contato",
}

ORIGEM = {"automatica": "automática", "manual": "manual"}

ESTADO_IRRIGACAO = {
    "iniciada": "em andamento",
    "concluida": "concluída",
    "cancelada": "cancelada",
    "interrompida": "interrompida",
}

RESULTADO_COMANDO = {
    "executado": "executado pela placa",
    "recusado_vencido": "recusado: chegou vencido",
    "recusado_em_andamento": "recusado: já havia uma irrigação em andamento",
    "cancelado": "cancelado",
    "recusado_invalido": "recusado: comando inválido",
}


def classe(valor: int | None) -> tuple[str, str]:
    return CLASSE.get(valor, SEM_CLASSE) if valor is not None else SEM_CLASSE


# ---------------------------------------------------------------- números e horas


def br(valor: float | int | None, casas: int = 1) -> str:
    if valor is None:
        return "—"
    return f"{valor:.{casas}f}".replace(".", ",")


def _instante(valor: str | int | float | None, fuso: ZoneInfo) -> datetime | None:
    if valor is None:
        return None
    if isinstance(valor, int | float):
        return datetime.fromtimestamp(valor, fuso)
    momento = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(fuso)


def hora(valor: str | int | float | None, fuso: ZoneInfo, agora: datetime | None = None) -> str:
    """'14:05' se for hoje; '10/11 14:05' se for outro dia."""
    momento = _instante(valor, fuso)
    if momento is None:
        return "—"
    hoje = (agora or datetime.now(fuso)).astimezone(fuso).date()
    if momento.date() == hoje:
        return momento.strftime("%H:%M")
    return momento.strftime("%d/%m %H:%M")


def dia(valor: str | date) -> str:
    """'2026-11-10' (dia local, sem conversão) → '10/11'."""
    d = date.fromisoformat(valor) if isinstance(valor, str) else valor
    return d.strftime("%d/%m")


def _minutos(valor: float | None) -> str:
    if valor is None:
        return "—"
    if valor >= 90:
        h, m = divmod(round(valor), 60)
        return f"{h} h {m:02d} min"
    casas = 0 if float(valor).is_integer() else 1
    return f"{br(valor, casas)} min"


# ---------------------------------------------------------------- telas


def titulo_cultivo(nome: str, fazenda: str | None = None) -> str:
    return f"<b>{esc(nome)}</b>" + (f" · {esc(fazenda)}" if fazenda else "")


def lista_cultivos(cultivos: list[dict[str, Any]], atual_id: int | None) -> str:
    if not cultivos:
        return (
            "Não encontrei nenhum cultivo na plataforma. "
            "Cadastre a fazenda e o cultivo pelo painel AgroEdge."
        )
    linhas = ["<b>Seus cultivos</b>"]
    for n, c in enumerate(cultivos, start=1):
        emoji, rotulo = classe(c.get("ultima_classe"))
        marca = " ← escolhido" if c["id"] == atual_id else ""
        linhas.append(f"{n}. {esc(c['nome'])} ({esc(c['fazenda_nome'])}) · {emoji} {rotulo}{marca}")
    linhas.append("\nToque num cultivo para escolher.")
    return "\n".join(linhas)


def resumo(r: dict[str, Any], fuso: ZoneInfo, agora: datetime | None = None) -> str:
    """A tela "/hoje": tudo de um cultivo, a partir de GET /api/cultivos/{id}/resumo."""
    c = r["cultivo"]
    ciclo = r.get("ciclo") or {}
    cultura = (c.get("cultura_info") or {}).get("nome") or c.get("cultura", "")
    linhas = [titulo_cultivo(c["nome"], (c.get("fazenda") or {}).get("nome"))]

    fase = f" · {esc(ciclo['fase_nome'])}" if ciclo.get("fase_nome") else ""
    if ciclo:
        linhas.append(
            f"{esc(cultura)} · dia {ciclo.get('dias')} de {ciclo.get('ciclo_dias')}{fase}"
        )
    if ciclo.get("fora_do_ciclo"):
        linhas.append("⚠️ Fora do ciclo da cultura: confira a data de poda/floração no painel.")
    linhas.append("")

    linhas += _bloco_diario(r.get("ultimo_diario"))
    linhas.append("")
    linhas += _bloco_tempo(r.get("ultima_leitura"), fuso, agora)
    linhas += _bloco_valvula(r.get("valvula") or {}, fuso, agora)
    linhas += _bloco_placa(r.get("dispositivo"), fuso, agora)
    return "\n".join(linhas)


def _linha_irrigar(d: dict[str, Any]) -> str:
    """A lâmina indicada pela placa no fechamento (o bot não recalcula)."""
    lamina = d.get("lamina_bruta")
    if lamina is None:
        return "💧 Irrigação indicada: — (a placa não calculou a lâmina)"
    if lamina <= 0:
        return "💧 <b>Não precisa irrigar</b> (lâmina indicada: 0 mm)"
    linha = f"💧 Irrigar: <b>{br(lamina)} mm</b>"
    if d.get("aplicar_l_planta") is not None:
        linha += f" · {br(d['aplicar_l_planta'])} L/planta"
    if d.get("minutos") is not None:
        linha += f" · {_minutos(d['minutos'])} de válvula"
    return linha


def _bloco_diario(d: dict[str, Any] | None) -> list[str]:
    if d is None:
        return [
            "⏳ Ainda não há fechamento diário.",
            "A placa fecha o dia à meia-noite e então indica a irrigação.",
        ]
    emoji, rotulo = classe(d.get("classe"))
    linhas = [
        f"{emoji} Estado hídrico: <b>{rotulo}</b> (fechamento de {dia(d['data'])})",
        _linha_irrigar(d),
        f"     ET₀ {br(d.get('et0'))} mm · ETc {br(d.get('etc'))} mm · Kc {br(d.get('kc'), 2)}",
    ]
    for aviso in (d.get("avisos") or [])[:3]:
        linhas.append(f"⚠️ <i>{esc(aviso)}</i>")
    return linhas


def _bloco_tempo(
    leitura: dict[str, Any] | None, fuso: ZoneInfo, agora: datetime | None
) -> list[str]:
    if leitura is None:
        return ["🌡 Sem leituras da estação ainda."]
    return [
        f"🌡 Clima ({hora(leitura.get('ts'), fuso, agora)}): "
        f"{br(leitura.get('temp_c'))} °C · UR {br(leitura.get('ur_pct'), 0)}% · "
        f"vento {br(leitura.get('vento_ms'))} m/s · chuva {br(leitura.get('chuva_mm'))} mm"
    ]


def _bloco_valvula(v: dict[str, Any], fuso: ZoneInfo, agora: datetime | None) -> list[str]:
    andamento = v.get("em_andamento")
    if v.get("aberta") and andamento:
        texto = (
            f"🚿 Válvula <b>aberta</b> desde {hora(andamento.get('ts_inicio'), fuso, agora)}"
            f" ({ORIGEM.get(andamento.get('origem'), andamento.get('origem'))}"
            + (f", {_minutos(andamento['minutos'])}" if andamento.get("minutos") else "")
            + ")"
        )
    elif v.get("aberta"):
        texto = "🚿 Válvula <b>aberta</b>"
    else:
        texto = "🚿 Válvula fechada"
        if v.get("proxima_prevista"):
            texto += f" · próxima prevista {hora(v['proxima_prevista'], fuso, agora)}"
    linhas = [texto]
    ultima = v.get("ultima")
    if ultima and not v.get("aberta"):
        linhas.append(
            f"     Última: {hora(ultima.get('ts_inicio'), fuso, agora)}, "
            f"{_minutos(ultima.get('minutos'))}"
            + (f", {br(ultima['mm'])} mm" if ultima.get("mm") is not None else "")
            + f" ({ORIGEM.get(ultima.get('origem'), ultima.get('origem'))})"
        )
    return linhas


def _bloco_placa(p: dict[str, Any] | None, fuso: ZoneInfo, agora: datetime | None) -> list[str]:
    if p is None:
        return ["📡 Nenhuma placa instalada neste cultivo."]
    status = p.get("status")
    nome = esc(p.get("apelido") or f"Placa {p.get('serial')}")
    if status == "ao_vivo":
        detalhe = f"ao vivo · {hora(p.get('ultima_telemetria'), fuso, agora)}"
    elif status == "sincronizando":
        detalhe = f"sincronizando ({p.get('sincronizando', 0)} leituras na fila)"
    elif status == "atrasado":
        detalhe = f"atrasada · última leitura {hora(p.get('ultima_telemetria'), fuso, agora)}"
    else:
        detalhe = f"sem contato desde {hora(p.get('ultimo_contato'), fuso, agora)}"
    aviso = "" if status in ("ao_vivo", "sincronizando") else " ⚠️"
    linhas = [f"📡 {nome}: {detalhe}{aviso}"]
    if p.get("cfg_aplicada") is False:
        linhas.append("     Configuração nova aguardando a placa confirmar.")
    return linhas


def historico(nome: str, diarios: list[dict[str, Any]]) -> str:
    linhas = [f"{titulo_cultivo(nome)} · fechamentos dos últimos 7 dias", ""]
    if not diarios:
        linhas.append("Nenhum fechamento diário no período.")
        return "\n".join(linhas)
    for d in sorted(diarios, key=lambda x: x["data"], reverse=True):
        emoji, rotulo = classe(d.get("classe"))
        linhas.append(
            f"<b>{dia(d['data'])}</b> {emoji} {rotulo}\n"
            f"     ETc {br(d.get('etc'))} · chuva {br(d.get('chuva'))} · "
            f"irrigado {br(d.get('irrigacao'))} · indicado {br(d.get('lamina_bruta'))} mm"
        )
    return "\n".join(linhas)


def irrigacoes(
    nome: str, lista: list[dict[str, Any]], fuso: ZoneInfo, agora: datetime | None = None
) -> str:
    linhas = [f"{titulo_cultivo(nome)} · irrigações dos últimos 7 dias", ""]
    if not lista:
        linhas.append("Nenhuma irrigação no período.")
        return "\n".join(linhas)
    ordenadas = sorted(lista, key=lambda x: x["ts_inicio"], reverse=True)
    for i in ordenadas[:15]:
        linhas.append(
            f"{hora(i['ts_inicio'], fuso, agora)} · {ORIGEM.get(i['origem'], i['origem'])} · "
            f"{_minutos(i.get('minutos'))}"
            + (f" · {br(i['mm'])} mm" if i.get("mm") is not None else "")
            + f" · {ESTADO_IRRIGACAO.get(i['estado'], i['estado'])}"
        )
    if len(ordenadas) > 15:
        linhas.append(f"… e mais {len(ordenadas) - 15} no painel.")
    return "\n".join(linhas)


def valvula(nome: str, r: dict[str, Any], fuso: ZoneInfo, agora: datetime | None = None) -> str:
    linhas = [titulo_cultivo(nome), ""]
    linhas += _bloco_valvula(r.get("valvula") or {}, fuso, agora)
    linhas += _bloco_placa(r.get("dispositivo"), fuso, agora)
    d = r.get("ultimo_diario")
    if d and d.get("minutos") is not None:
        linhas.append(
            f"\n💧 Indicado no último fechamento: {br(d.get('lamina_bruta'))} mm "
            f"({_minutos(d['minutos'])} de válvula)"
        )
    if r.get("dispositivo"):
        linhas.append("\nEscolha uma ação. Vou pedir confirmação antes de abrir a água.")
    return "\n".join(linhas)


def confirmar(nome: str, acao: str, minutos: float | None) -> str:
    if acao == "abrir":
        return f"Abrir a válvula de {titulo_cultivo(nome)} por <b>{_minutos(minutos)}</b>?"
    return f"Fechar a válvula de {titulo_cultivo(nome)} agora?"


def comando_enviado(nome: str, acao: str, minutos: float | None) -> str:
    o_que = f"abrir por {_minutos(minutos)}" if acao == "abrir" else "fechar"
    return f"📨 Comando para {o_que} enviado a {titulo_cultivo(nome)}. Aguardando a placa…"


def comando_respondido(
    nome: str, acao: str, minutos: float | None, estado: str, resultado: str | None
) -> str:
    if estado == "executado":
        if acao == "abrir":
            return f"✅ Válvula de {titulo_cultivo(nome)} aberta por {_minutos(minutos)}."
        return f"✅ Válvula de {titulo_cultivo(nome)} fechada."
    if estado == "expirado":
        return (
            f"⌛ A placa de {titulo_cultivo(nome)} não respondeu em 10 minutos. "
            "O comando expirou e não será executado."
        )
    motivo = RESULTADO_COMANDO.get(resultado or "", resultado or "recusado")
    return f"❌ A placa de {titulo_cultivo(nome)} não executou o comando: {esc(motivo)}."


# ---------------------------------------------------------------- alertas (SSE)


def alerta_diario(nome: str, d: dict[str, Any]) -> str:
    emoji, rotulo = classe(d.get("classe"))
    linhas = [
        f"📊 Fechamento de {dia(d['data'])} · {titulo_cultivo(nome)}",
        f"{emoji} Estado hídrico: <b>{rotulo}</b>",
        _linha_irrigar(d),
    ]
    if d.get("classe") == 2:
        linhas.append("Atenção: o solo está com déficit crítico de água.")
    for aviso in (d.get("avisos") or [])[:2]:
        linhas.append(f"⚠️ <i>{esc(aviso)}</i>")
    return "\n".join(linhas)


def alerta_status(nome: str, serial: str, status: str) -> str:
    if status == "offline":
        return (
            f"⚠️ A placa {esc(serial)} ({titulo_cultivo(nome)}) ficou <b>sem contato</b>. "
            "As leituras ficam guardadas nela e chegam quando ela voltar."
        )
    return f"📡 A placa {esc(serial)} ({titulo_cultivo(nome)}) voltou a se conectar."


def alerta_irrigacao(nome: str, dados: dict[str, Any]) -> str | None:
    estado = dados.get("estado")
    origem = ORIGEM.get(dados.get("origem", ""), dados.get("origem", ""))
    minutos = dados.get("minutos")
    if estado == "iniciada":
        return (
            f"🚿 Irrigação {origem} começou em {titulo_cultivo(nome)}"
            + (f" ({_minutos(minutos)})" if minutos else "")
            + "."
        )
    if estado == "concluida":
        return (
            f"✅ Irrigação {origem} concluída em {titulo_cultivo(nome)}"
            + (f": {_minutos(minutos)} de válvula" if minutos is not None else "")
            + "."
        )
    if estado in ("cancelada", "interrompida"):
        return (
            f"⏹ Irrigação {origem} {ESTADO_IRRIGACAO[estado]} em {titulo_cultivo(nome)}"
            + (f" depois de {_minutos(minutos)}" if minutos is not None else "")
            + "."
        )
    return None


# ---------------------------------------------------------------- ajuda


AJUDA = """<b>AgroEdge</b>: irrigação de precisão na palma da mão.

<b>Hoje</b>: estado hídrico, quanto irrigar e o clima agora
<b>Válvula</b>: abrir ou fechar a válvula (com confirmação)
<b>Histórico</b>: fechamentos dos últimos 7 dias
<b>Irrigações</b>: irrigações dos últimos 7 dias
<b>Cultivos</b>: escolher o cultivo
<b>Alertas</b>: ligar ou desligar os avisos automáticos
<b>Desconectar</b>: tirar esta conversa da conta

Use os botões abaixo ou escreva o comando (por exemplo, <i>abrir 10</i> para abrir a \
válvula por 10 minutos, ou <i>fechar</i>).
Os cálculos são feitos pela placa na lavoura; o bot só repassa."""


def nao_conectada() -> str:
    return (
        "Olá! Sou o bot do <b>AgroEdge</b>.\n\n"
        "Esta conversa ainda não está conectada a uma conta. Para conectar:\n"
        "1. Entre no painel AgroEdge e abra <b>Conta</b>.\n"
        "2. No cartão <b>Telegram</b>, toque em <b>Conectar Telegram</b>.\n"
        "3. Aponte a câmera do celular para o QR code (ou toque em <i>Abrir no Telegram</i>)."
    )


def conectada(usuario_nome: str | None) -> str:
    conta = f" à conta de <b>{esc(usuario_nome)}</b>" if usuario_nome else ""
    return (
        f"✅ Pronto! Esta conversa está conectada{conta}.\n"
        "Você vai receber aqui os alertas da lavoura.\n\n" + AJUDA
    )


CONFIRMAR_DESCONECTAR = (
    "Desconectar esta conversa da conta AgroEdge?\n"
    "Você deixa de receber os alertas e não consegue mais abrir a válvula por aqui."
)

DESCONECTADA = (
    "Conversa desconectada. Para conectar de novo, gere um QR code no painel "
    "(<b>Conta → Telegram</b>)."
)
