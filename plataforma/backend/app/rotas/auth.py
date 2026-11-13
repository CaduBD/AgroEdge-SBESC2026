"""Login por e-mail e senha, sessão em cookie assinado."""

import math

from fastapi import APIRouter, Request
from sqlmodel import col, select

from app.auth import (
    Sessao,
    UsuarioAtual,
    abrir_sessao,
    conferir_login,
    conferir_senha,
    gerar_hash_senha,
)
from app.config import obter_settings
from app.erros import ErroApp
from app.limite_login import LimiteLogin
from app.models import Usuario
from app.schemas.api import LoginEntrada, Ok, TrocaSenhaEntrada, UsuarioSaida

rotas = APIRouter(prefix="/api/auth", tags=["autenticação"])

_settings = obter_settings()
limite_login = LimiteLogin(_settings.login_max_falhas, _settings.login_janela_min * 60)
FATOR_EMAIL = 4  # o e-mail aguenta 4x mais falhas que um IP (veja limite_login.py)


def _chaves(request: Request, email: str) -> tuple[str, str]:
    # Atrás do Caddy, o Uvicorn troca o IP do proxy pelo do visitante (X-Forwarded-For),
    # desde que o proxy esteja em FORWARDED_ALLOW_IPS.
    ip = request.client.host if request.client else "desconhecido"
    return f"ip:{ip}", f"email:{email}"


@rotas.post(
    "/login",
    response_model=UsuarioSaida,
    responses={429: {"description": "Muitas tentativas erradas; espere alguns minutos."}},
)
async def login(entrada: LoginEntrada, request: Request, sessao: Sessao) -> Usuario:
    email = entrada.email.strip().lower()
    chave_ip, chave_email = _chaves(request, email)
    espera = limite_login.espera_s(
        [(chave_ip, limite_login.max_falhas), (chave_email, limite_login.max_falhas * FATOR_EMAIL)]
    )
    if espera > 0:
        minutos = max(1, math.ceil(espera / 60))
        raise ErroApp(
            429,
            "muitas_tentativas",
            f"Muitas tentativas erradas. Tente de novo em {minutos} min.",
        )
    usuario = (
        await sessao.execute(select(Usuario).where(col(Usuario.email) == email))
    ).scalar_one_or_none()
    if not conferir_login(usuario, entrada.senha) or usuario is None:
        limite_login.falhou([chave_ip, chave_email])
        raise ErroApp(401, "credenciais_invalidas", "E-mail ou senha incorretos.")
    limite_login.acertou([chave_ip, chave_email])
    abrir_sessao(request, usuario)
    return usuario


@rotas.post("/logout", response_model=Ok)
async def logout(request: Request) -> Ok:
    request.session.clear()
    return Ok()


@rotas.get("/eu", response_model=UsuarioSaida)
async def eu(usuario: UsuarioAtual) -> Usuario:
    return usuario


@rotas.patch("/senha", response_model=Ok)
async def trocar_senha(
    entrada: TrocaSenhaEntrada, request: Request, usuario: UsuarioAtual, sessao: Sessao
) -> Ok:
    """Troca a senha. As outras sessões abertas (outro navegador, celular) caem; esta continua."""
    if not conferir_senha(usuario.senha_hash, entrada.senha_atual):
        raise ErroApp(400, "senha_atual_incorreta", "A senha atual está incorreta.")
    usuario.senha_hash = gerar_hash_senha(entrada.senha_nova)
    usuario.sessao_versao += 1
    sessao.add(usuario)
    await sessao.commit()
    abrir_sessao(request, usuario)
    return Ok()
