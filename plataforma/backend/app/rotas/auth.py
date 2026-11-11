"""Login por e-mail e senha, sessão em cookie assinado."""

from fastapi import APIRouter, Request
from sqlmodel import col, select

from app.auth import CHAVE_SESSAO, Sessao, UsuarioAtual, conferir_senha, gerar_hash_senha
from app.erros import ErroApp
from app.models import Usuario
from app.schemas.api import LoginEntrada, Ok, TrocaSenhaEntrada, UsuarioSaida

rotas = APIRouter(prefix="/api/auth", tags=["autenticação"])


@rotas.post("/login", response_model=UsuarioSaida)
async def login(entrada: LoginEntrada, request: Request, sessao: Sessao) -> Usuario:
    usuario = (
        await sessao.execute(
            select(Usuario).where(col(Usuario.email) == entrada.email.strip().lower())
        )
    ).scalar_one_or_none()
    if usuario is None or not conferir_senha(usuario.senha_hash, entrada.senha):
        raise ErroApp(401, "credenciais_invalidas", "E-mail ou senha incorretos.")
    request.session.clear()
    request.session[CHAVE_SESSAO] = usuario.id
    return usuario


@rotas.post("/logout", response_model=Ok)
async def logout(request: Request) -> Ok:
    request.session.clear()
    return Ok()


@rotas.get("/eu", response_model=UsuarioSaida)
async def eu(usuario: UsuarioAtual) -> Usuario:
    return usuario


@rotas.patch("/senha", response_model=Ok)
async def trocar_senha(entrada: TrocaSenhaEntrada, usuario: UsuarioAtual, sessao: Sessao) -> Ok:
    if not conferir_senha(usuario.senha_hash, entrada.senha_atual):
        raise ErroApp(400, "senha_atual_incorreta", "A senha atual está incorreta.")
    usuario.senha_hash = gerar_hash_senha(entrada.senha_nova)
    sessao.add(usuario)
    await sessao.commit()
    return Ok()
