"""Canal de terminal: conversa com o núcleo pelo teclado, sem Telegram.

Serve para desenvolver e testar contra o simulador (e mostra que o núcleo não depende
do canal). Botões aparecem numerados: digite o número para "tocar".
"""

from __future__ import annotations

import asyncio
import html
import re

from agroedge_bot.nucleo.mensagens import Botao, Resposta, para_texto_simples
from agroedge_bot.nucleo.servico import Servico

CONVERSA = "console"


def mostrar(resposta: Resposta, titulo: str | None = None) -> list[Botao]:
    if titulo:
        print(f"\n── {titulo} " + "─" * max(0, 50 - len(titulo)))
    else:
        print()
    texto = para_texto_simples(resposta.texto, negrito="", italico="")
    print(html.unescape(re.sub(r"<[^>]+>", "", texto)))
    botoes = [b for linha in resposta.botoes for b in linha]
    if botoes:
        print("  " + "  ".join(f"[{n}] {b.rotulo}" for n, b in enumerate(botoes, start=1)))
    return botoes


class CanalConsole:
    def __init__(self) -> None:
        self.servico: Servico | None = None

    async def enviar(self, conversa: str, resposta: Resposta) -> None:
        mostrar(resposta, titulo="alerta")

    async def rodar(self) -> None:
        assert self.servico is not None
        print("AgroEdge no terminal. Escreva como no Telegram (hoje, válvula, abrir 10…).")
        print("Número = tocar no botão. Ctrl+C ou 'sair' para encerrar.")
        botoes = mostrar(await self.servico.tratar_texto(CONVERSA, "ajuda"))
        while True:
            try:
                linha = (await asyncio.to_thread(input, "\n> ")).strip()
            except EOFError:
                return
            if linha in ("sair", "exit", "quit"):
                return
            if linha.isdigit() and 1 <= int(linha) <= len(botoes):
                resposta = await self.servico.tratar_botao(CONVERSA, botoes[int(linha) - 1].dado)
            else:
                resposta = await self.servico.tratar_texto(CONVERSA, linha)
            botoes = mostrar(resposta)
