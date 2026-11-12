"""Vínculo de conversas do chatbot (Telegram) com usuários da plataforma.

Fluxo:
1. O chatbot, ao ligar, registra o @ do bot (`PUT /api/canais/telegram/bot`).
2. No painel, o usuário pede um código (`POST /api/canais/telegram/codigo`) e recebe o link
   `https://t.me/<bot>?start=<codigo>`, que o painel mostra como QR code.
3. O produtor abre o link; o Telegram manda `/start <codigo>` ao bot, que chama
   `POST /api/canais/telegram/vincular`. A conversa fica ligada ao usuário.
4. Daí em diante o bot manda `X-Conversa: telegram:<chat id>` em cada pedido e a API
   responde como aquele usuário (mesmas regras de posse do painel).
"""

import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Response
from sqlmodel import col, select

from app.auth import (
    Sessao,
    TokenChatbot,
    UsuarioAtual,
    VinculoAtual,
    cultivo_do_usuario,
)
from app.erros import ErroApp, nao_encontrado
from app.models import BotCanal, Canal, CodigoVinculo, Usuario, VinculoCanal, agora_utc
from app.schemas.api import (
    BotEntrada,
    BotSaida,
    CodigoSaida,
    ConversaEdicao,
    ConversaSaida,
    SituacaoCodigo,
    VincularEntrada,
    VinculoSaida,
)

rotas = APIRouter(prefix="/api/canais", tags=["chatbot"])

VALIDADE_CODIGO = timedelta(minutes=10)


def _link(canal: Canal, usuario_bot: str, codigo: str) -> str:
    # Só há Telegram por enquanto; o WhatsApp teria o seu formato de link aqui.
    return f"https://t.me/{usuario_bot}?start={codigo}"


async def _bot(sessao: Sessao, canal: Canal) -> BotCanal | None:
    return await sessao.get(BotCanal, canal)


async def _conversa_saida(sessao: Sessao, vinculo: VinculoCanal) -> ConversaSaida:
    usuario = await sessao.get(Usuario, vinculo.usuario_id)
    return ConversaSaida(
        canal=vinculo.canal,
        conversa_id=vinculo.conversa_id,
        usuario_id=vinculo.usuario_id,
        usuario_nome=usuario.nome if usuario else "",
        alertas=vinculo.alertas,
        cultivo_id=vinculo.cultivo_id,
    )


# Rotas com caminho fixo vêm antes das com {canal}: o FastAPI usa a primeira que casar.

# ---------------------------------------------------------------- painel: conversas da conta


@rotas.get("/vinculos", response_model=list[VinculoSaida])
async def listar_vinculos(usuario: UsuarioAtual, sessao: Sessao) -> list[VinculoCanal]:
    """Conversas conectadas à conta (painel: Conta → Telegram)."""
    return list(
        (
            await sessao.execute(
                select(VinculoCanal)
                .where(col(VinculoCanal.usuario_id) == usuario.id)
                .order_by(col(VinculoCanal.criado_em))
            )
        ).scalars()
    )


@rotas.delete("/vinculos/{vinculo_id}", status_code=204)
async def desconectar(vinculo_id: int, usuario: UsuarioAtual, sessao: Sessao) -> Response:
    vinculo = await sessao.get(VinculoCanal, vinculo_id)
    if vinculo is None or vinculo.usuario_id != usuario.id:
        raise nao_encontrado("Conversa")
    await sessao.delete(vinculo)
    await sessao.commit()
    return Response(status_code=204)


@rotas.get("/codigos/{codigo}", response_model=SituacaoCodigo)
async def situacao_do_codigo(codigo: str, usuario: UsuarioAtual, sessao: Sessao) -> SituacaoCodigo:
    """Se o QR code já foi usado e por qual conversa (o painel consulta a cada 2 s)."""
    registro = await sessao.get(CodigoVinculo, codigo)
    if registro is None or registro.usuario_id != usuario.id:
        raise nao_encontrado("Código")
    vinculo = await sessao.get(VinculoCanal, registro.vinculo_id) if registro.vinculo_id else None
    return SituacaoCodigo(
        expira_em=registro.expira_em,
        usado_em=registro.usado_em,
        vinculo=VinculoSaida.model_validate(vinculo) if vinculo else None,
    )


# ---------------------------------------------------------------- a conversa do X-Conversa


@rotas.get("/conversa", response_model=ConversaSaida)
async def conversa_atual(vinculo: VinculoAtual, sessao: Sessao) -> ConversaSaida:
    return await _conversa_saida(sessao, vinculo)


@rotas.patch("/conversa", response_model=ConversaSaida)
async def editar_conversa(
    entrada: ConversaEdicao, vinculo: VinculoAtual, usuario: UsuarioAtual, sessao: Sessao
) -> ConversaSaida:
    """Preferências da conversa: alertas ligados e cultivo escolhido."""
    dados: dict[str, Any] = entrada.model_dump(exclude_unset=True)
    if dados.get("alertas") is not None:
        vinculo.alertas = dados["alertas"]
    if "cultivo_id" in dados:
        cultivo_id = dados["cultivo_id"]
        if cultivo_id:
            await cultivo_do_usuario(sessao, usuario, cultivo_id)  # 404 se não for dele
        vinculo.cultivo_id = cultivo_id or None
    sessao.add(vinculo)
    await sessao.commit()
    return await _conversa_saida(sessao, vinculo)


@rotas.delete("/conversa", status_code=204)
async def desconectar_conversa(vinculo: VinculoAtual, sessao: Sessao) -> Response:
    """O produtor pediu para desconectar pelo próprio bot."""
    await sessao.delete(vinculo)
    await sessao.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- painel: bot e QR code


@rotas.get("/{canal}", response_model=BotSaida)
async def bot_do_canal(canal: Canal, _usuario: UsuarioAtual, sessao: Sessao) -> BotSaida:
    """Qual bot atende o canal (nulo se o chatbot ainda não foi ligado)."""
    bot = await _bot(sessao, canal)
    return BotSaida(canal=canal, usuario_bot=bot.usuario_bot if bot else None)


@rotas.post("/{canal}/codigo", response_model=CodigoSaida, status_code=201)
async def gerar_codigo(canal: Canal, usuario: UsuarioAtual, sessao: Sessao) -> CodigoSaida:
    """Código de uso único (10 min) e o link que o painel mostra como QR code."""
    bot = await _bot(sessao, canal)
    if bot is None:
        raise ErroApp(
            409,
            "bot_desligado",
            "O chatbot ainda não foi ligado. Inicie o bot e tente de novo.",
        )
    agora = agora_utc()
    # Códigos vencidos ou já usados deste usuário não servem mais para nada.
    antigos = (
        await sessao.execute(
            select(CodigoVinculo).where(
                col(CodigoVinculo.usuario_id) == usuario.id,
                (col(CodigoVinculo.expira_em) < agora) | col(CodigoVinculo.usado_em).is_not(None),
            )
        )
    ).scalars()
    for antigo in antigos:
        await sessao.delete(antigo)
    codigo = CodigoVinculo(
        codigo=secrets.token_urlsafe(12),  # 16 caracteres [A-Za-z0-9_-]: aceito pelo Telegram
        usuario_id=usuario.id,  # type: ignore[arg-type]
        canal=canal,
        criado_em=agora,
        expira_em=agora + VALIDADE_CODIGO,
    )
    sessao.add(codigo)
    await sessao.commit()
    return CodigoSaida(
        codigo=codigo.codigo,
        link=_link(canal, bot.usuario_bot, codigo.codigo),
        usuario_bot=bot.usuario_bot,
        expira_em=codigo.expira_em,
    )


# ---------------------------------------------------------------- só o chatbot


@rotas.put("/{canal}/bot", response_model=BotSaida)
async def registrar_bot(
    canal: Canal, entrada: BotEntrada, _token: TokenChatbot, sessao: Sessao
) -> BotSaida:
    """O chatbot informa o seu @ ao ligar (o painel monta o link com ele)."""
    bot = await _bot(sessao, canal)
    if bot is None:
        bot = BotCanal(canal=canal, usuario_bot=entrada.usuario_bot)
    bot.usuario_bot = entrada.usuario_bot
    bot.atualizado_em = agora_utc()
    sessao.add(bot)
    await sessao.commit()
    return BotSaida(canal=canal, usuario_bot=bot.usuario_bot)


@rotas.post("/{canal}/vincular", response_model=ConversaSaida)
async def vincular(
    canal: Canal, entrada: VincularEntrada, _token: TokenChatbot, sessao: Sessao
) -> ConversaSaida:
    """Troca o código do QR code pelo vínculo da conversa (o `/start <codigo>` do bot)."""
    codigo = await sessao.get(CodigoVinculo, entrada.codigo.strip())
    agora = agora_utc()
    if codigo is None or codigo.canal != canal:
        raise ErroApp(404, "codigo_invalido", "Código inválido. Gere um novo QR code no painel.")
    if codigo.usado_em is not None:
        raise ErroApp(409, "codigo_usado", "Este QR code já foi usado. Gere outro no painel.")
    if codigo.expira_em < agora:
        raise ErroApp(410, "codigo_expirado", "Este QR code venceu. Gere outro no painel.")
    codigo.usado_em = agora
    sessao.add(codigo)
    vinculo = (
        await sessao.execute(
            select(VinculoCanal).where(
                col(VinculoCanal.canal) == canal,
                col(VinculoCanal.conversa_id) == entrada.conversa_id,
            )
        )
    ).scalar_one_or_none()
    if vinculo is None:
        vinculo = VinculoCanal(
            usuario_id=codigo.usuario_id, canal=canal, conversa_id=entrada.conversa_id
        )
    elif vinculo.usuario_id != codigo.usuario_id:
        # A mesma conversa passa para outra conta: o que era da conta anterior não vale.
        vinculo.usuario_id = codigo.usuario_id
        vinculo.cultivo_id = None
        vinculo.alertas = True
    vinculo.nome = entrada.nome or vinculo.nome
    vinculo.ultimo_uso = agora
    sessao.add(vinculo)
    await sessao.flush()
    codigo.vinculo_id = vinculo.id
    await sessao.commit()
    return await _conversa_saida(sessao, vinculo)


@rotas.get("/{canal}/conversas", response_model=list[ConversaSaida])
async def todas_as_conversas(
    canal: Canal, _token: TokenChatbot, sessao: Sessao
) -> list[ConversaSaida]:
    """Todas as conversas vinculadas do canal (o bot decide a quem mandar cada alerta)."""
    vinculos = (
        await sessao.execute(
            select(VinculoCanal)
            .where(col(VinculoCanal.canal) == canal)
            .order_by(col(VinculoCanal.id))
        )
    ).scalars()
    return [await _conversa_saida(sessao, v) for v in vinculos]
