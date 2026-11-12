"""Canal Telegram (aiogram 3). Só traduz: mensagem/botão → núcleo → mensagem/botão.

Usa long polling: o bot busca as mensagens no Telegram, então roda em qualquer máquina
com internet (inclusive o notebook da equipe), sem IP público, domínio ou HTTPS.
"""

from __future__ import annotations

import contextlib
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from agroedge_bot.canais import ErroCanal
from agroedge_bot.nucleo.mensagens import Resposta
from agroedge_bot.nucleo.servico import MENU, Servico

log = logging.getLogger("telegram")

COMANDOS = [
    BotCommand(command="hoje", description="Estado hídrico, irrigação indicada e clima"),
    BotCommand(command="valvula", description="Abrir ou fechar a válvula"),
    BotCommand(command="historico", description="Fechamentos dos últimos 7 dias"),
    BotCommand(command="irrigacoes", description="Irrigações dos últimos 7 dias"),
    BotCommand(command="cultivos", description="Escolher o cultivo"),
    BotCommand(command="alertas", description="Ligar ou desligar os alertas"),
    BotCommand(command="desconectar", description="Tirar esta conversa da conta"),
    BotCommand(command="ajuda", description="O que o bot faz"),
]

TECLADO_MENU = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=t) for t in linha] for linha in MENU],
    resize_keyboard=True,
    is_persistent=True,
)


def nome_da_conversa(mensagem: Message) -> str | None:
    """Como a conversa aparece no painel: "Carlos Diniz (@cadu)" ou o título do grupo."""
    if mensagem.chat.type != "private":
        return mensagem.chat.title
    pessoa = mensagem.from_user
    if pessoa is None:
        return None
    return pessoa.full_name + (f" (@{pessoa.username})" if pessoa.username else "")


def marcacao(
    resposta: Resposta,
) -> InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove:
    """Mensagem nova: os botões dela; sem botões, o menu fixo (ou tira o menu)."""
    return teclado(resposta) or (TECLADO_MENU if resposta.menu else ReplyKeyboardRemove())


def teclado(resposta: Resposta) -> InlineKeyboardMarkup | None:
    if not resposta.botoes:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=b.rotulo, callback_data=b.dado) for b in linha]
            for linha in resposta.botoes
        ]
    )


class CanalTelegram:
    def __init__(self, token: str, proxy: str | None = None) -> None:
        sessao = AiohttpSession(proxy=proxy) if proxy else None
        self.bot = Bot(
            token, session=sessao, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self._servico: Servico | None = None
        roteador = Router()
        roteador.message.register(self._ao_texto, F.text)
        roteador.callback_query.register(self._ao_botao, F.data)
        self.dp.include_router(roteador)

    @property
    def servico(self) -> Servico:
        if self._servico is None:
            raise RuntimeError("CanalTelegram.servico não foi definido")
        return self._servico

    @servico.setter
    def servico(self, valor: Servico) -> None:
        self._servico = valor

    # ------------------------------------------------------------ saída

    async def enviar(self, conversa: str, resposta: Resposta) -> None:
        """Mensagem que o produtor não pediu agora: alertas e resposta da placa."""
        try:
            await self.bot.send_message(
                int(conversa), resposta.texto, reply_markup=teclado(resposta)
            )
        except TelegramForbiddenError:
            log.warning("conversa %s bloqueou o bot ou nunca deu /start", conversa)

    # ------------------------------------------------------------ entrada

    async def _ao_texto(self, mensagem: Message) -> None:
        conversa = str(mensagem.chat.id)
        await self.bot.send_chat_action(mensagem.chat.id, ChatAction.TYPING)
        resposta = await self.servico.tratar_texto(
            conversa, mensagem.text or "", nome_da_conversa(mensagem)
        )
        await mensagem.answer(resposta.texto, reply_markup=marcacao(resposta))

    async def _ao_botao(self, toque: CallbackQuery) -> None:
        mensagem = toque.message
        if mensagem is None or not isinstance(mensagem, Message):
            await toque.answer("Mensagem antiga demais. Use o menu.", show_alert=True)
            return
        conversa = str(mensagem.chat.id)
        await toque.answer()  # tira o "carregando" do botão
        resposta = await self.servico.tratar_botao(conversa, toque.data or "")
        # Edita a própria mensagem (a confirmação vira "comando enviado", "Atualizar"
        # atualiza no lugar). Se não der para editar, manda uma nova.
        if resposta.nova_mensagem:
            await mensagem.answer(resposta.texto, reply_markup=marcacao(resposta))
            return
        try:
            await mensagem.edit_text(resposta.texto, reply_markup=teclado(resposta))
        except TelegramBadRequest as erro:
            if "message is not modified" in str(erro):
                return
            await mensagem.answer(resposta.texto, reply_markup=teclado(resposta))

    # ------------------------------------------------------------ ciclo de vida

    async def preparar(self) -> str:
        """Confere o token, publica os comandos do menu e devolve o @ do bot."""
        try:
            eu = await self.bot.get_me()
        except TelegramUnauthorizedError as erro:
            raise ErroCanal(
                "O Telegram recusou o TELEGRAM_BOT_TOKEN. Confira o token com o @BotFather."
            ) from erro
        except TelegramNetworkError as erro:
            raise ErroCanal(
                f"Não consegui falar com o Telegram ({erro.message}). Confira a internet."
            ) from erro
        log.info("telegram conectado como @%s", eu.username)
        await self.bot.set_my_commands(COMANDOS)
        return eu.username or ""

    async def rodar(self) -> None:
        await self.dp.start_polling(self.bot, handle_signals=False)

    async def fechar(self) -> None:
        with contextlib.suppress(RuntimeError):  # RuntimeError: o polling nem começou
            await self.dp.stop_polling()
        await self.bot.session.close()
