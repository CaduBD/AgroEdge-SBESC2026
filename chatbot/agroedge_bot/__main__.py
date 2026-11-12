"""Ponto de entrada: `python -m agroedge_bot [--console | --verificar]`.

- sem opção: bot do Telegram + alertas do SSE;
- `--console`: conversa no terminal, sem Telegram (bom para testar com o simulador);
- `--verificar`: confere a configuração e a API, lista os cultivos e sai.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from typing import Protocol
from zoneinfo import ZoneInfo

from agroedge_bot.canais import ErroCanal
from agroedge_bot.config import Settings, obter_settings
from agroedge_bot.nucleo.acesso import Acesso, AcessoLocal, AcessoPlataforma
from agroedge_bot.nucleo.api import ClienteAgroEdge, ErroApi
from agroedge_bot.nucleo.estado import Estado
from agroedge_bot.nucleo.mensagens import Resposta
from agroedge_bot.nucleo.servico import Servico
from agroedge_bot.nucleo.sse import ouvir_para_sempre

log = logging.getLogger("agroedge_bot")


class Canal(Protocol):
    servico: Servico

    async def enviar(self, conversa: str, resposta: Resposta) -> None: ...
    async def rodar(self) -> None: ...


DICAS = {
    "token_invalido": "confira o AGROEDGE_TOKEN (é o CHATBOT_TOKEN do .env da plataforma)",
    "escopo_insuficiente": "o token não é o do chatbot: rode de novo o seed da plataforma",
    "nao_encontrado": "a plataforma está desatualizada: rode .\\tarefas.ps1 up em plataforma",
    "metodo_nao_permitido": "a plataforma está desatualizada: rode .\\tarefas.ps1 up em plataforma",
}


async def verificar(s: Settings) -> int:
    print(f"API: {s.agroedge_api_url}")
    if not s.agroedge_token:
        print("✗ AGROEDGE_TOKEN vazio (use o CHATBOT_TOKEN do .env da plataforma)")
        return 1
    api = ClienteAgroEdge(s.agroedge_api_url, s.agroedge_token)
    try:
        saude = await api.saude()
        print(f"✓ plataforma no ar (broker conectado: {saude.get('mqtt_conectado')})")
        servico = Servico(AcessoLocal(api, set(), Estado()), Estado(), _sem_envio)
        cultivos = await servico.listar_cultivos(api)
        print(f"✓ token aceito; {len(cultivos)} cultivo(s) do dono do token:")
        for c in cultivos:
            serial = (c.get("configuracao") or {}).get("serial") or "sem placa"
            print(f"   - {c['nome']} ({c['fazenda_nome']}) · {serial}")
        conversas = await api.conversas("telegram")
        print(f"✓ vínculo de conversas ativo; {len(conversas)} conversa(s) do Telegram:")
        for c in conversas:
            alertas = "alertas ligados" if c["alertas"] else "alertas desligados"
            print(f"   - {c['conversa_id']} → {c['usuario_nome']} ({alertas})")
    except ErroApi as erro:
        dica = DICAS.get(erro.codigo)
        print(f"✗ {erro.mensagem} ({erro.codigo})" + (f": {dica}" if dica else ""))
        return 1
    finally:
        await api.fechar()
    if s.telegram_bot_token:
        print("✓ TELEGRAM_BOT_TOKEN preenchido")
    else:
        print("• TELEGRAM_BOT_TOKEN vazio (só o modo --console funciona)")
    print(f"• alertas: {sorted(s.bot_alertas) or 'nenhum'}")
    return 0


async def _sem_envio(conversa: str, resposta: Resposta) -> None:
    return None


async def rodar(s: Settings, console: bool) -> int:
    if not s.agroedge_token:
        log.error("AGROEDGE_TOKEN vazio: use o CHATBOT_TOKEN do .env da plataforma")
        return 1
    api = ClienteAgroEdge(s.agroedge_api_url, s.agroedge_token)
    canal: Canal
    acesso: Acesso
    if console:
        from agroedge_bot.canais.console import CONVERSA, CanalConsole

        canal = CanalConsole()  # type: ignore[assignment]
        estado = Estado.carregar(None)  # o terminal não guarda nada entre execuções
        acesso = AcessoLocal(api, {CONVERSA}, estado)
        url_sse = f"{api.url}/api/stream"  # eventos do dono do token
    else:
        if not s.telegram_bot_token:
            log.error("TELEGRAM_BOT_TOKEN vazio: crie o bot com o @BotFather (veja o README)")
            await api.fechar()
            return 1
        from agroedge_bot.canais.telegram import CanalTelegram

        telegram = CanalTelegram(s.telegram_bot_token, proxy=s.telegram_proxy or None)
        canal = telegram  # type: ignore[assignment]
        estado = Estado.carregar(s.bot_arquivo_estado)
        acesso = AcessoPlataforma(api, "telegram")
        url_sse = f"{api.url}/api/stream?todos=true"  # eventos de todas as contas
        try:
            usuario_bot = await telegram.preparar()
            # O painel monta o link do QR code com o @ do bot.
            await api.registrar_bot("telegram", usuario_bot)
        except ErroCanal as erro:
            log.error("%s", erro)
            await telegram.fechar()
            await api.fechar()
            return 1
        except ErroApi as erro:
            dica = DICAS.get(erro.codigo, "")
            log.error("a plataforma recusou o registro do bot: %s (%s)", erro.mensagem, dica)
            await telegram.fechar()
            await api.fechar()
            return 1

    servico = Servico(acesso, estado, canal.enviar, s.bot_alertas, ZoneInfo(s.bot_fuso))
    canal.servico = servico

    try:
        await servico.sincronizar(avisar=True)
    except ErroApi as erro:
        log.warning("plataforma indisponível ao iniciar: %s (o bot segue tentando)", erro.mensagem)

    sse = asyncio.create_task(
        ouvir_para_sempre(url_sse, api.cabecalhos, servico.ao_evento, servico.ao_reconectar)
    )
    try:
        await canal.rodar()
    finally:
        sse.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sse
        await servico.encerrar()
        await api.fechar()
        fechar = getattr(canal, "fechar", None)
        if fechar is not None:
            await fechar()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="agroedge_bot", description=__doc__.split("\n")[0])
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--console", action="store_true", help="conversar pelo terminal")
    modo.add_argument("--verificar", action="store_true", help="conferir configuração e API")
    parser.add_argument("-v", "--verboso", action="store_true", help="logs de depuração")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verboso else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.console:  # no terminal, os logs atrapalham a conversa
        logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if sys.platform == "win32":
        # Acentos e emojis no terminal do Windows
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    s = obter_settings()
    try:
        if args.verificar:
            codigo = asyncio.run(verificar(s))
        else:
            codigo = asyncio.run(rodar(s, args.console))
    except KeyboardInterrupt:
        codigo = 0
    sys.exit(codigo)


if __name__ == "__main__":
    main()
