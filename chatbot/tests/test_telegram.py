"""O adaptador do Telegram de ponta a ponta, sem rede: updates falsos entram pelo
Dispatcher e as chamadas à API do Telegram ficam registradas numa sessão falsa."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageText,
    SendChatAction,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import Message, ReplyKeyboardRemove, Update

from agroedge_bot.canais.telegram import CanalTelegram
from agroedge_bot.nucleo.servico import Servico

CHAT = 100


class SessaoFalsa(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.chamadas: list[TelegramMethod[Any]] = []

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.chamadas.append(method)
        if isinstance(method, SendMessage | EditMessageText):
            return Message.model_validate(
                {
                    "message_id": 1,
                    "date": datetime.now(),
                    "chat": {"id": CHAT, "type": "private"},
                    "text": method.text,
                }
            )
        return True

    async def close(self) -> None: ...

    async def stream_content(
        self, *a: Any, **k: Any
    ) -> AsyncGenerator[bytes, None]:  # pragma: no cover
        yield b""

    def enviadas(self) -> list[Any]:
        return [c for c in self.chamadas if isinstance(c, SendMessage | EditMessageText)]


def canal_de_teste(servico: Servico) -> tuple[CanalTelegram, SessaoFalsa]:
    canal = CanalTelegram("42:TESTE")
    sessao = SessaoFalsa()
    canal.bot.session = sessao
    canal.servico = servico
    return canal, sessao


def mensagem(texto: str, chat: int = CHAT) -> Update:
    return Update.model_validate(
        {"update_id": 1, "message": {
            "message_id": 10, "date": int(datetime.now().timestamp()), "text": texto,
            "chat": {"id": chat, "type": "private"},
            "from": {"id": chat, "is_bot": False, "first_name": "Produtor"},
        }}
    )  # fmt: skip


def toque(dado: str) -> Update:
    return Update.model_validate(
        {"update_id": 2, "callback_query": {
            "id": "cb1", "chat_instance": "x", "data": dado,
            "from": {"id": CHAT, "is_bot": False, "first_name": "Produtor"},
            "message": {"message_id": 11, "date": int(datetime.now().timestamp()), "text": "antes",
                        "chat": {"id": CHAT, "type": "private"}},
        }}
    )  # fmt: skip


async def test_texto_com_menu_fixo(servico: Servico) -> None:
    canal, sessao = canal_de_teste(servico)
    await canal.dp.feed_update(canal.bot, mensagem("/ajuda"))
    assert any(isinstance(c, SendChatAction) for c in sessao.chamadas)
    enviada = sessao.enviadas()[-1]
    assert "AgroEdge" in enviada.text
    assert enviada.reply_markup.keyboard[0][0].text == "Hoje"  # menu fixo


async def test_hoje_vem_com_botoes(servico: Servico) -> None:
    canal, sessao = canal_de_teste(servico)
    await canal.dp.feed_update(canal.bot, mensagem("Hoje"))
    enviada = sessao.enviadas()[-1]
    assert "Estado hídrico" in enviada.text
    assert enviada.reply_markup.inline_keyboard[0][0].callback_data == "sel:hoje:2"


async def test_botao_edita_a_mensagem(servico: Servico) -> None:
    canal, sessao = canal_de_teste(servico)
    await canal.dp.feed_update(canal.bot, toque("no"))
    assert isinstance(sessao.chamadas[0], AnswerCallbackQuery)
    editada = sessao.chamadas[-1]
    assert isinstance(editada, EditMessageText) and "nada foi feito" in editada.text


async def test_botao_de_alerta_manda_nova_mensagem(servico: Servico) -> None:
    canal, sessao = canal_de_teste(servico)
    await canal.dp.feed_update(canal.bot, toque("n:hoje:2"))
    assert isinstance(sessao.chamadas[-1], SendMessage)
    assert "Estado hídrico" in sessao.chamadas[-1].text


async def test_conversa_nao_conectada_recebe_instrucoes_sem_menu(servico: Servico) -> None:
    canal, sessao = canal_de_teste(servico)
    await canal.dp.feed_update(canal.bot, mensagem("/start", chat=555))
    enviada = sessao.enviadas()[-1]
    assert "Conectar Telegram" in enviada.text
    assert isinstance(enviada.reply_markup, ReplyKeyboardRemove)


async def test_start_com_codigo_conecta(servico_plat: Servico, plataforma) -> None:
    plataforma.codigos["AbC_123-xyz"] = 1
    canal, sessao = canal_de_teste(servico_plat)
    await canal.dp.feed_update(canal.bot, mensagem("/start AbC_123-xyz", chat=555))
    enviada = sessao.enviadas()[-1]
    assert "conectada à conta de <b>Equipe</b>" in enviada.text
    assert enviada.reply_markup.keyboard[0][0].text == "Hoje"
    # o nome que aparece no painel vem do Telegram
    assert plataforma.vinculos["555"]["nome"] == "Produtor"


async def test_enviar_alerta(servico: Servico) -> None:
    canal, sessao = canal_de_teste(servico)
    from agroedge_bot.nucleo.mensagens import Resposta

    await canal.enviar("100", Resposta("⚠️ alerta"))
    enviada = sessao.enviadas()[-1]
    assert enviada.chat_id == 100 and enviada.text == "⚠️ alerta"
