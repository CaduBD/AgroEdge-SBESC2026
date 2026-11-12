"""O cérebro do bot, sem nada de Telegram: entende o que o produtor pediu, consulta a API
e devolve `Resposta`s; trata os eventos do SSE e manda os alertas.

Um canal (Telegram hoje, WhatsApp no futuro) só precisa:
1. entregar o texto recebido a `tratar_texto` e o toque num botão a `tratar_botao`;
2. mostrar a `Resposta` devolvida;
3. oferecer a função `enviar(conversa_id, resposta)`, usada para alertas e para a resposta
   da placa a um comando (mensagens que o produtor não pediu naquele momento).

Quem pode usar e o que cada conversa escolheu vem do `Acesso` (no Telegram, da plataforma:
o produtor conecta a conversa pelo QR code do painel e manda `/start <codigo>`).
"""

from __future__ import annotations

import asyncio
import logging
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agroedge_bot.nucleo import textos
from agroedge_bot.nucleo.acesso import Acesso, Conversa
from agroedge_bot.nucleo.api import ClienteAgroEdge, ErroApi
from agroedge_bot.nucleo.estado import Estado
from agroedge_bot.nucleo.mensagens import Botao, Resposta
from agroedge_bot.nucleo.sse import EventoSse

log = logging.getLogger("servico")

Enviar = Callable[[str, Resposta], Awaitable[None]]

# Menu fixo (o Telegram mostra como teclado; no WhatsApp viraria uma lista de opções).
MENU = [["Hoje", "Válvula"], ["Histórico", "Irrigações"], ["Cultivos", "Alertas"]]

ATALHOS_ABRIR = (5, 10, 20, 30)
MINUTOS_MIN, MINUTOS_MAX = 1, 120  # mesmos limites da API
VALIDADE_CONFIRMACAO_S = 120  # botão "Sim, abrir" antigo não abre a água dias depois
ACOMPANHAR_COMANDO_S = 12 * 60  # a API expira o comando em 10 min
INTERVALO_CONSULTA_S = 20.0

# Palavras que o produtor pode escrever (sem acento, minúsculas) → ação
COMANDOS = {
    "start": "ajuda", "ajuda": "ajuda", "help": "ajuda", "menu": "ajuda", "oi": "ajuda",
    "ola": "ajuda", "bom": "ajuda", "boa": "ajuda",
    "hoje": "hoje", "resumo": "hoje", "status": "hoje",
    "cultivos": "cultivos", "cultivo": "cultivos", "trocar": "cultivos",
    "historico": "hist", "fechamentos": "hist",
    "irrigacoes": "irr", "irrigacao": "irr",
    "valvula": "valv", "agua": "valv",
    "abrir": "abrir", "irrigar": "abrir", "ligar": "abrir",
    "fechar": "fechar", "cancelar": "fechar", "desligar": "fechar", "parar": "fechar",
    "alertas": "alertas", "alerta": "alertas", "avisos": "alertas",
    "desconectar": "desconectar", "sair": "desconectar",
}  # fmt: skip


@dataclass
class Pendente:
    """Comando enviado à placa que ainda não teve resposta."""

    conversa: str
    serial: str
    nome: str
    acao: str
    minutos: float | None


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


class NaoConectada(Exception):
    """A conversa não está (ou deixou de estar) conectada a uma conta."""


class Servico:
    def __init__(
        self,
        acesso: Acesso,
        estado: Estado,
        enviar: Enviar,
        alertas: set[str] | None = None,
        fuso: ZoneInfo | None = None,
        relogio: Callable[[], float] = time.time,
        intervalo_consulta_s: float = INTERVALO_CONSULTA_S,
    ) -> None:
        self.acesso = acesso
        self.estado = estado
        self.enviar = enviar
        self.alertas = {"diario", "status", "irrigacao"} if alertas is None else alertas
        self.fuso = fuso or ZoneInfo("America/Bahia")
        self.relogio = relogio
        self.intervalo_consulta_s = intervalo_consulta_s
        self._nomes: dict[int, str] = {}
        self._pendentes: dict[str, Pendente] = {}
        self._confirmacoes_usadas: set[str] = set()
        self._tarefas: set[asyncio.Task[None]] = set()

    def _api(self, conversa: str) -> ClienteAgroEdge:
        return self.acesso.api(conversa)

    async def _conectada(self, conversa: str) -> Conversa:
        conv = await self.acesso.conversa(conversa)
        if conv is None:
            raise NaoConectada
        return conv

    # ================================================================ entrada

    async def tratar_texto(self, conversa: str, texto: str, nome: str | None = None) -> Resposta:
        """`nome`: como a pessoa aparece no app (fica registrado no painel ao conectar)."""
        palavras = normalizar(texto).lstrip("/").split()
        primeira = palavras[0].split("@")[0] if palavras else ""  # "/hoje@Bot" em grupos
        argumento = palavras[1] if len(palavras) > 1 else None
        try:
            if primeira == "start" and argumento:
                # Veio do QR code do painel: /start <codigo> (o código diferencia maiúsculas)
                return await self._vincular(conversa, texto.split()[1], nome)
            await self._conectada(conversa)
            if not palavras:
                return Resposta(textos.AJUDA)
            return await self._executar_texto(conversa, COMANDOS.get(primeira), argumento)
        except NaoConectada:
            return Resposta(textos.nao_conectada(), menu=False)
        except ErroApi as erro:
            if erro.codigo == "conversa_nao_vinculada":
                return Resposta(textos.nao_conectada(), menu=False)
            return Resposta(f"❌ {erro.mensagem}")

    async def tratar_botao(self, conversa: str, dado: str) -> Resposta:
        partes = dado.split(":")
        try:
            await self._conectada(conversa)
            match partes:
                case ["sel" | "n" as tipo, acao, cid]:
                    await self.acesso.escolher_cultivo(conversa, int(cid))
                    resposta = await self._por_cultivo(conversa, acao, int(cid))
                    resposta.nova_mensagem = tipo == "n"
                    return resposta
                case ["cult"]:
                    return await self._cultivos(conversa)
                case ["v", "a", cid, minutos]:
                    return await self._confirmacao(conversa, int(cid), "abrir", float(minutos))
                case ["v", "f", cid]:
                    return await self._confirmacao(conversa, int(cid), "cancelar", None)
                case ["ok", "a" | "f" as a, cid, minutos, ts]:
                    acao = "abrir" if a == "a" else "cancelar"
                    return await self._executar_comando(
                        conversa, dado, int(cid), acao, float(minutos) or None, int(ts)
                    )
                case ["no"]:
                    return Resposta("Tudo bem, nada foi feito.")
                case ["al", liga]:
                    return await self._alertas(conversa, liga == "1")
                case ["dc"]:
                    await self.acesso.desvincular(conversa)
                    return Resposta(textos.DESCONECTADA, menu=False)
        except NaoConectada:
            return Resposta(textos.nao_conectada(), menu=False)
        except ErroApi as erro:
            if erro.codigo == "conversa_nao_vinculada":
                return Resposta(textos.nao_conectada(), menu=False)
            return Resposta(f"❌ {erro.mensagem}")
        except ValueError:
            pass
        log.warning("botão desconhecido %r", dado)
        return Resposta("Esse botão não vale mais. " + "Use o menu abaixo.")

    async def _executar_texto(
        self, conversa: str, acao: str | None, argumento: str | None
    ) -> Resposta:
        if acao == "ajuda":
            return Resposta(textos.AJUDA)
        if acao == "alertas":
            if argumento in ("on", "ligar", "sim", "ligado"):
                return await self._alertas(conversa, True)
            if argumento in ("off", "desligar", "nao", "desligado"):
                return await self._alertas(conversa, False)
            return await self._alertas(conversa, None)
        if acao == "desconectar":
            return Resposta(
                textos.CONFIRMAR_DESCONECTAR,
                [[Botao("Sim, desconectar", "dc"), Botao("Não", "no")]],
            )
        if acao == "cultivos":
            if argumento and argumento.isdigit():
                return await self._escolher_por_numero(conversa, int(argumento))
            return await self._cultivos(conversa)
        if acao in ("hoje", "hist", "irr", "valv", "abrir", "fechar"):
            escolha = await self._cultivo_da_conversa(conversa, acao)
            if isinstance(escolha, Resposta):
                return escolha
            cid = escolha["id"]
            if acao == "abrir":
                minutos = _ler_minutos(argumento)
                if minutos is None:
                    return await self._por_cultivo(conversa, "valv", cid)
                return await self._confirmacao(conversa, cid, "abrir", minutos)
            if acao == "fechar":
                return await self._confirmacao(conversa, cid, "cancelar", None)
            return await self._por_cultivo(conversa, acao, cid)
        return Resposta("Não entendi. 🤔\n\n" + textos.AJUDA)

    async def _vincular(self, conversa: str, codigo: str, nome: str | None) -> Resposta:
        try:
            conv = await self.acesso.vincular(conversa, codigo, nome)
        except ErroApi as erro:
            return Resposta(f"❌ {erro.mensagem}", menu=False)
        log.info("conversa %s conectada ao usuário %s", conversa, conv.usuario_id)
        return Resposta(textos.conectada(conv.usuario_nome))

    # ================================================================ cultivos

    async def listar_cultivos(self, api: ClienteAgroEdge) -> list[dict[str, Any]]:
        """Os cultivos de quem a `api` representa (fazendas → cultivos; nunca IDs fixos)."""
        lista: list[dict[str, Any]] = []
        for fazenda in await api.fazendas():
            for cultivo in await api.cultivos_da_fazenda(fazenda["id"]):
                cultivo["fazenda_nome"] = fazenda["nome"]
                lista.append(cultivo)
                self._nomes[cultivo["id"]] = cultivo["nome"]
        return lista

    async def _cultivos(self, conversa: str) -> Resposta:
        cultivos = await self.listar_cultivos(self._api(conversa))
        atual = (await self._conectada(conversa)).cultivo_id
        botoes = [[Botao(c["nome"][:40], f"sel:hoje:{c['id']}")] for c in cultivos]
        return Resposta(textos.lista_cultivos(cultivos, atual), botoes)

    async def _escolher_por_numero(self, conversa: str, numero: int) -> Resposta:
        cultivos = await self.listar_cultivos(self._api(conversa))
        if not 1 <= numero <= len(cultivos):
            atual = (await self._conectada(conversa)).cultivo_id
            return Resposta(
                f"Não há cultivo número {numero}.\n\n" + textos.lista_cultivos(cultivos, atual)
            )
        cultivo = cultivos[numero - 1]
        await self.acesso.escolher_cultivo(conversa, cultivo["id"])
        return await self._por_cultivo(conversa, "hoje", cultivo["id"])

    async def _cultivo_da_conversa(self, conversa: str, proximo: str) -> dict[str, Any] | Resposta:
        """O cultivo escolhido nesta conversa; se não há um (ou sumiu), pede para escolher."""
        cultivos = await self.listar_cultivos(self._api(conversa))
        if not cultivos:
            return Resposta(textos.lista_cultivos([], None))
        conv = await self._conectada(conversa)
        for cultivo in cultivos:
            if cultivo["id"] == conv.cultivo_id:
                return cultivo
        if len(cultivos) == 1:
            await self.acesso.escolher_cultivo(conversa, cultivos[0]["id"])
            return cultivos[0]
        seguinte = proximo if proximo in ("hoje", "hist", "irr", "valv") else "valv"
        botoes = [[Botao(c["nome"][:40], f"sel:{seguinte}:{c['id']}")] for c in cultivos]
        return Resposta("De qual cultivo?", botoes)

    async def nome_cultivo(self, cultivo_id: int | None, api: ClienteAgroEdge) -> str:
        if cultivo_id is None:
            return "cultivo"
        if cultivo_id not in self._nomes:
            try:
                self._nomes[cultivo_id] = (await api.cultivo(cultivo_id))["nome"]
            except ErroApi:
                return f"cultivo {cultivo_id}"
        return self._nomes[cultivo_id]

    # ================================================================ telas

    async def _por_cultivo(self, conversa: str, acao: str, cid: int) -> Resposta:
        api = self._api(conversa)
        if acao == "hoje":
            return await self._hoje(api, cid)
        if acao == "hist":
            return await self._historico(api, cid)
        if acao == "irr":
            return await self._irrigacoes(api, cid)
        return await self._valvula(api, cid)

    def _navegacao(self, cid: int, atual: str) -> list[list[Botao]]:
        opcoes = [("hoje", "📋 Hoje"), ("valv", "🚿 Válvula"), ("hist", "📅 Histórico")]
        linha = [
            Botao("🔄 Atualizar" if a == atual else rotulo, f"sel:{a}:{cid}")
            for a, rotulo in opcoes
        ]
        return [linha]

    async def _hoje(self, api: ClienteAgroEdge, cid: int) -> Resposta:
        resumo = await api.resumo(cid)
        self._nomes[cid] = resumo["cultivo"]["nome"]
        return Resposta(textos.resumo(resumo, self.fuso), self._navegacao(cid, "hoje"))

    async def _historico(self, api: ClienteAgroEdge, cid: int) -> Resposta:
        de = (self._hoje_local() - timedelta(days=6)).isoformat()
        diarios = await api.diarios(cid, de=de)
        nome = await self.nome_cultivo(cid, api)
        return Resposta(textos.historico(nome, diarios), self._navegacao(cid, "hist"))

    async def _irrigacoes(self, api: ClienteAgroEdge, cid: int) -> Resposta:
        de = (self._hoje_local() - timedelta(days=6)).isoformat()
        lista = await api.irrigacoes(cid, de=de)
        nome = await self.nome_cultivo(cid, api)
        return Resposta(textos.irrigacoes(nome, lista, self.fuso), self._navegacao(cid, "irr"))

    async def _valvula(self, api: ClienteAgroEdge, cid: int) -> Resposta:
        resumo = await api.resumo(cid)
        nome = resumo["cultivo"]["nome"]
        self._nomes[cid] = nome
        botoes: list[list[Botao]] = []
        if resumo.get("dispositivo"):
            botoes.append([Botao(f"Abrir {m} min", f"v:a:{cid}:{m}") for m in ATALHOS_ABRIR])
            indicado = (resumo.get("ultimo_diario") or {}).get("minutos")
            if indicado is not None and MINUTOS_MIN <= round(indicado) <= MINUTOS_MAX:
                m = round(indicado)
                botoes.append([Botao(f"💧 Abrir {m} min (indicado)", f"v:a:{cid}:{m}")])
            botoes.append([Botao("⏹ Fechar válvula", f"v:f:{cid}")])
        botoes += self._navegacao(cid, "valv")
        return Resposta(textos.valvula(nome, resumo, self.fuso), botoes)

    async def _alertas(self, conversa: str, ligar: bool | None) -> Resposta:
        if ligar is not None:
            await self.acesso.definir_alertas(conversa, ligar)
        conv = await self._conectada(conversa)
        tipos = {
            "diario": "fechamento do dia (meia-noite)",
            "status": "placa sem contato",
            "irrigacao": "início e fim das irrigações",
        }
        ativos = [tipos[t] for t in ("diario", "status", "irrigacao") if t in self.alertas]
        if conv.alertas:
            texto = (
                "🔔 Alertas <b>ligados</b> nesta conversa.\nVocê recebe: "
                + ("; ".join(ativos) or "nenhum tipo está ativo no bot")
                + "."
            )
            botao = Botao("🔕 Desligar alertas", "al:0")
        else:
            texto = "🔕 Alertas <b>desligados</b> nesta conversa."
            botao = Botao("🔔 Ligar alertas", "al:1")
        return Resposta(texto, [[botao]])

    # ================================================================ válvula

    async def _confirmacao(
        self, conversa: str, cid: int, acao: str, minutos: float | None
    ) -> Resposta:
        if acao == "abrir" and (minutos is None or not MINUTOS_MIN <= minutos <= MINUTOS_MAX):
            return Resposta(
                f"Informe de {MINUTOS_MIN} a {MINUTOS_MAX} minutos (por exemplo, <i>abrir 10</i>)."
            )
        nome = await self.nome_cultivo(cid, self._api(conversa))
        agora = int(self.relogio())
        a = "a" if acao == "abrir" else "f"
        sim = "✅ Sim, abrir" if acao == "abrir" else "✅ Sim, fechar"
        dado = f"ok:{a}:{cid}:{_num(minutos)}:{agora}"
        return Resposta(
            textos.confirmar(nome, acao, minutos), [[Botao(sim, dado), Botao("Não", "no")]]
        )

    async def _executar_comando(
        self,
        conversa: str,
        dado: str,
        cid: int,
        acao: str,
        minutos: float | None,
        criado_em: int,
    ) -> Resposta:
        if self.relogio() - criado_em > VALIDADE_CONFIRMACAO_S:
            return Resposta("⌛ Essa confirmação venceu. Peça de novo pelo menu <b>Válvula</b>.")
        if dado in self._confirmacoes_usadas:
            return Resposta("Esse comando já foi enviado.")
        self._confirmacoes_usadas.add(dado)
        api = self._api(conversa)
        resumo = await api.resumo(cid)
        nome = resumo["cultivo"]["nome"]
        dispositivo = resumo.get("dispositivo")
        if not dispositivo:
            return Resposta(f"Nenhuma placa instalada em {textos.titulo_cultivo(nome)}.")
        serial = dispositivo["serial"]
        try:
            comando = await api.enviar_comando(serial, acao, minutos)
        except ErroApi as erro:
            self._confirmacoes_usadas.discard(dado)  # nada foi enviado: pode tentar de novo
            return Resposta(f"❌ {erro.mensagem}")
        pendente = Pendente(conversa, serial, nome, acao, minutos)
        if comando.get("estado", "enviado") != "enviado":  # improvável, mas já respondido
            return Resposta(
                textos.comando_respondido(
                    nome, acao, minutos, comando["estado"], comando.get("resultado")
                )
            )
        self._pendentes[comando["id"]] = pendente
        self._iniciar(self._acompanhar_comando(comando["id"]))
        log.info("comando enviado serial=%s acao=%s minutos=%s", serial, acao, minutos)
        return Resposta(textos.comando_enviado(nome, acao, minutos))

    async def _resolver_comando(self, cmd_id: str, estado: str, resultado: str | None) -> None:
        pendente = self._pendentes.pop(cmd_id, None)
        if pendente is None:
            return  # comando do painel, ou já avisado
        log.info("comando respondido id=%s estado=%s", cmd_id, estado)
        texto = textos.comando_respondido(
            pendente.nome, pendente.acao, pendente.minutos, estado, resultado
        )
        await self.enviar(pendente.conversa, Resposta(texto))

    async def _acompanhar_comando(self, cmd_id: str) -> None:
        """Plano B do SSE: se o evento `comando` não chegar, consulta a API até ter resposta."""
        limite = self.relogio() + ACOMPANHAR_COMANDO_S
        while cmd_id in self._pendentes and self.relogio() < limite:
            await asyncio.sleep(self.intervalo_consulta_s)
            pendente = self._pendentes.get(cmd_id)
            if pendente is None:
                return
            try:
                lista = await self._api(pendente.conversa).comandos(pendente.serial)
            except ErroApi:
                continue
            for c in lista:
                if c["id"] == cmd_id and c["estado"] != "enviado":
                    await self._resolver_comando(cmd_id, c["estado"], c.get("resultado"))
                    return
        if cmd_id in self._pendentes:
            await self._resolver_comando(cmd_id, "expirado", None)

    # ================================================================ alertas (SSE)

    async def ao_evento(self, evento: EventoSse) -> None:
        if evento.tipo == "comando":
            estado = evento.dados.get("estado")
            if estado and estado != "enviado":
                await self._resolver_comando(
                    str(evento.dados.get("id")), estado, evento.dados.get("resultado")
                )
        elif evento.tipo == "diario":
            await self._evento_diario(evento)
        elif evento.tipo == "status":
            await self._evento_status(evento)
        elif evento.tipo == "irrigacao" and "irrigacao" in self.alertas:
            if self._abertura_pedida_pelo_bot(evento):
                return  # quem pediu recebe "Válvula aberta" pela resposta do comando
            conversas = await self._conversas_do_dono(evento)
            if not conversas:
                return
            nome = await self.nome_cultivo(evento.cultivo_id, self._api(conversas[0].id))
            texto = textos.alerta_irrigacao(nome, evento.dados)
            if texto:
                await self._avisar(conversas, Resposta(texto))

    async def _conversas_do_dono(self, evento: EventoSse) -> list[Conversa]:
        """Conversas conectadas à conta dona do evento (a plataforma manda `usuario_id`)."""
        dono = evento.dados.get("usuario_id")
        return [
            c
            for c in await self.acesso.todas()
            if dono is None or c.usuario_id is None or c.usuario_id == dono
        ]

    def _abertura_pedida_pelo_bot(self, evento: EventoSse) -> bool:
        return (
            evento.dados.get("estado") == "iniciada"
            and evento.dados.get("origem") == "manual"
            and any(
                p.serial == evento.serial and p.acao == "abrir" for p in self._pendentes.values()
            )
        )

    async def _evento_diario(self, evento: EventoSse) -> None:
        cid, data = evento.cultivo_id, evento.dados.get("data")
        if cid is None or not data:
            return
        if not self._diario_novo(cid, data):
            return
        if "diario" not in self.alertas:
            return
        conversas = await self._conversas_do_dono(evento)
        if not conversas:
            return
        api = self._api(conversas[0].id)
        # O evento traz o essencial; o fechamento completo tem litros por planta e avisos.
        completo = dict(evento.dados)
        try:
            for d in await api.diarios(cid, de=data):
                if d["data"] == data:
                    completo = d
        except ErroApi:
            pass
        await self._avisar_diario(conversas, cid, completo)

    def _diario_novo(self, cid: int, data: str) -> bool:
        """Registra o fechamento; falso se ele já tinha sido avisado."""
        anterior = self.estado.ultimo_diario.get(str(cid))
        if anterior is not None and data <= anterior:
            return False
        self.estado.ultimo_diario[str(cid)] = data
        self.estado.salvar()
        return True

    async def _avisar_diario(
        self, conversas: list[Conversa], cid: int, diario: dict[str, Any]
    ) -> None:
        nome = await self.nome_cultivo(cid, self._api(conversas[0].id))
        botoes = [[Botao("📋 Ver hoje", f"n:hoje:{cid}"), Botao("🚿 Válvula", f"n:valv:{cid}")]]
        await self._avisar(conversas, Resposta(textos.alerta_diario(nome, diario), botoes))

    async def _evento_status(self, evento: EventoSse) -> None:
        serial, status = evento.serial, evento.dados.get("status")
        if not serial or status not in ("online", "offline"):
            return
        anterior = self.estado.status_placa.get(serial)
        if anterior == status:
            return
        self.estado.status_placa[serial] = status
        self.estado.salvar()
        if "status" not in self.alertas:
            return
        if status == "online" and anterior is None:
            return  # primeira notícia da placa: nada a avisar
        conversas = await self._conversas_do_dono(evento)
        if not conversas:
            return
        nome = await self.nome_cultivo(evento.cultivo_id, self._api(conversas[0].id))
        await self._avisar(conversas, Resposta(textos.alerta_status(nome, serial, status)))

    async def _avisar(self, conversas: list[Conversa], resposta: Resposta) -> None:
        """Manda o alerta às conversas que estão com os alertas ligados."""
        for conversa in conversas:
            if not conversa.alertas:
                continue
            try:
                await self.enviar(conversa.id, resposta)
            except Exception:
                log.exception("falha ao enviar alerta para %s", conversa.id)

    async def sincronizar(self, avisar: bool = True) -> None:
        """Busca pela API o que o SSE pode ter perdido (ao iniciar e a cada reconexão).

        Fechamento diário mais novo que o último avisado gera o alerta. Na primeira vez
        que o bot vê um cultivo, só anota a data (não manda alerta de coisa antiga).
        Cada conta conectada é consultada com uma das suas conversas.
        """
        por_dono: dict[int | None, list[Conversa]] = {}
        for conversa in await self.acesso.todas():
            por_dono.setdefault(conversa.usuario_id, []).append(conversa)
        for conversas in por_dono.values():
            api = self._api(conversas[0].id)
            for cultivo in await self.listar_cultivos(api):
                cid = cultivo["id"]
                diario = (await api.resumo(cid)).get("ultimo_diario")
                if not diario:
                    continue
                primeira_vez = str(cid) not in self.estado.ultimo_diario
                novo = self._diario_novo(cid, diario["data"])
                if novo and avisar and not primeira_vez and "diario" in self.alertas:
                    await self._avisar_diario(conversas, cid, diario)

    async def ao_reconectar(self) -> None:
        log.info("sse reconectado: conferindo o que pode ter sido perdido")
        await self.sincronizar(avisar=True)
        # Comandos pendentes têm o próprio acompanhamento pela API (_acompanhar_comando).

    # ================================================================ utilidades

    def _hoje_local(self) -> date:
        return datetime.fromtimestamp(self.relogio(), self.fuso).date()

    def _iniciar(self, corrotina: Awaitable[None]) -> None:
        tarefa = asyncio.ensure_future(corrotina)
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)

    async def encerrar(self) -> None:
        for tarefa in list(self._tarefas):
            tarefa.cancel()
        await asyncio.gather(*self._tarefas, return_exceptions=True)


def _ler_minutos(texto: str | None) -> float | None:
    if not texto:
        return None
    try:
        return float(texto.replace(",", ".").removesuffix("min"))
    except ValueError:
        return None


def _num(valor: float | None) -> str:
    if valor is None:
        return "0"
    return str(int(valor)) if float(valor).is_integer() else str(valor)
