"""Autenticação e checagem de posse.

- `usuario_atual`: resolve o usuário pelo cookie de sessão **ou** pelo cabeçalho
  `Authorization: Bearer <token>` (token de serviço, seção 10.1).
- `garantir_acesso_*`: a **única** checagem de posse. Toda rota que recebe
  `fazenda_id`, `cultivo_id` ou `serial` passa por uma delas. Recurso de outro
  usuário responde 404, igual a recurso inexistente (não revela que existe).
"""

import hashlib
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.db import obter_sessao
from app.erros import ErroApp, nao_encontrado
from app.models import Cultivo, Dispositivo, Fazenda, TokenServico, Usuario, agora_utc

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False, description="Token de serviço (CHATBOT_TOKEN)")

CHAVE_SESSAO = "usuario_id"


# ---------------------------------------------------------------- hashes


def gerar_hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def conferir_senha(senha_hash: str, senha: str) -> bool:
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerificationError, InvalidHashError):
        return False


def gerar_hash_token(token: str) -> str:
    """Tokens de serviço são longos e aleatórios: SHA-256 basta e permite busca direta."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- usuário atual

Sessao = Annotated[AsyncSession, Depends(obter_sessao)]


async def usuario_atual(
    request: Request,
    sessao: Sessao,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Usuario:
    if credenciais is not None:
        token = (
            await sessao.execute(
                select(TokenServico).where(
                    col(TokenServico.token_hash) == gerar_hash_token(credenciais.credentials)
                )
            )
        ).scalar_one_or_none()
        if token is None:
            raise ErroApp(401, "token_invalido", "Token de acesso inválido.")
        token.ultimo_uso = agora_utc()
        sessao.add(token)
        await sessao.commit()
        usuario = await sessao.get(Usuario, token.usuario_id)
    else:
        usuario_id = request.session.get(CHAVE_SESSAO)
        usuario = await sessao.get(Usuario, usuario_id) if usuario_id else None
        if usuario is None:
            request.session.clear()
    if usuario is None:
        raise ErroApp(401, "nao_autenticado", "Faça login para continuar.")
    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


# ---------------------------------------------------------------- posse (funções)


async def fazenda_do_usuario(sessao: AsyncSession, usuario: Usuario, fazenda_id: int) -> Fazenda:
    fazenda = await sessao.get(Fazenda, fazenda_id)
    if fazenda is None or fazenda.usuario_id != usuario.id:
        raise nao_encontrado("Fazenda")
    return fazenda


async def cultivo_do_usuario(sessao: AsyncSession, usuario: Usuario, cultivo_id: int) -> Cultivo:
    resultado = await sessao.execute(
        select(Cultivo)
        .join(Fazenda, col(Fazenda.id) == col(Cultivo.fazenda_id))
        .where(col(Cultivo.id) == cultivo_id, col(Fazenda.usuario_id) == usuario.id)
    )
    cultivo = resultado.scalar_one_or_none()
    if cultivo is None:
        raise nao_encontrado("Cultivo")
    return cultivo


async def dispositivo_do_usuario(
    sessao: AsyncSession, usuario: Usuario, serial: str
) -> Dispositivo:
    disp = (
        await sessao.execute(select(Dispositivo).where(col(Dispositivo.serial) == serial))
    ).scalar_one_or_none()
    if disp is None or disp.usuario_id != usuario.id:
        raise nao_encontrado("Dispositivo")
    return disp


# ---------------------------------------------------------------- posse (dependências)


async def garantir_acesso_fazenda(
    fazenda_id: int, usuario: UsuarioAtual, sessao: Sessao
) -> Fazenda:
    return await fazenda_do_usuario(sessao, usuario, fazenda_id)


async def garantir_acesso_cultivo(
    cultivo_id: int, usuario: UsuarioAtual, sessao: Sessao
) -> Cultivo:
    return await cultivo_do_usuario(sessao, usuario, cultivo_id)


async def garantir_acesso_dispositivo(
    serial: str, usuario: UsuarioAtual, sessao: Sessao
) -> Dispositivo:
    return await dispositivo_do_usuario(sessao, usuario, serial)


FazendaDoUsuario = Annotated[Fazenda, Depends(garantir_acesso_fazenda)]
CultivoDoUsuario = Annotated[Cultivo, Depends(garantir_acesso_cultivo)]
DispositivoDoUsuario = Annotated[Dispositivo, Depends(garantir_acesso_dispositivo)]
