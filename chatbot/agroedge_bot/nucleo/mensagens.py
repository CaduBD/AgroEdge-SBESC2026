"""O que o núcleo devolve aos canais: texto e botões, sem nada de Telegram ou WhatsApp.

O texto usa só `<b>`, `<i>` e `<code>` (HTML simples). O Telegram aceita como está; um adaptador de
WhatsApp troca por `*negrito*` e `_itálico_` (veja `para_texto_simples`).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Botao:
    rotulo: str
    dado: str  # até 64 bytes (limite do callback_data do Telegram)

    def __post_init__(self) -> None:
        if len(self.dado.encode()) > 64:
            raise ValueError(f"dado do botão longo demais: {self.dado!r}")


@dataclass
class Resposta:
    texto: str
    botoes: list[list[Botao]] = field(default_factory=list)
    # Resposta a um botão: por padrão o canal edita a mensagem do botão; True = nova mensagem
    # (p.ex. "Ver hoje" num alerta não deve apagar o alerta).
    nova_mensagem: bool = False
    # Mensagem sem botões: True mostra o menu fixo; False tira o menu (conversa não
    # conectada, ou acabou de desconectar).
    menu: bool = True


def esc(texto: object) -> str:
    """Escapa nomes vindos da plataforma antes de pôr no texto com marcação."""
    return html.escape(str(texto), quote=False)


def para_texto_simples(texto: str, negrito: str = "*", italico: str = "_") -> str:
    """Converte a marcação do núcleo para canais sem HTML (WhatsApp, SMS)."""
    texto = re.sub(r"</?b>", negrito, texto)
    texto = re.sub(r"</?i>", italico, texto)
    texto = re.sub(r"</?code>", "", texto)
    return html.unescape(texto)
