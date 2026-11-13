"""Aplicação FastAPI: API, SSE, ingestor MQTT e tarefas periódicas (no lifespan).

A partir da fase 3, também serve o build do frontend.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth import Sessao, _bearer, usuario_atual
from app.config import obter_settings
from app.db import fabrica_sessao
from app.erros import ErroApp
from app.eventos import barramento
from app.models import agora_utc
from app.mqtt.ingestor import Ingestor
from app.mqtt.publicador import Publicador
from app.rotas import auth, canais, cultivos, dispositivos, fazendas, stream
from app.schemas.api import Erro
from app.servicos.comandos import expirar_comandos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

INTERVALO_EXPIRACAO_S = 60
SESSAO_DIAS = 30


async def _expirar_periodicamente() -> None:
    """Regra 9.5: a cada minuto, comandos vencidos sem resposta viram `expirado`."""
    while True:
        try:
            async with fabrica_sessao() as sessao:
                for evento in await expirar_comandos(sessao, agora_utc()):
                    barramento.publicar(evento)
        except Exception:
            log.exception("erro ao expirar comandos")
        await asyncio.sleep(INTERVALO_EXPIRACAO_S)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = obter_settings()
    tarefas: list[asyncio.Task[None]] = []
    ingestor = Ingestor(settings)
    app.state.ingestor = ingestor
    if not hasattr(app.state, "publicador"):  # os testes colocam um publicador falso
        app.state.publicador = Publicador(lambda: ingestor.cliente)
    if settings.mqtt_habilitado:
        tarefas.append(asyncio.create_task(ingestor.rodar(), name="ingestor-mqtt"))
        tarefas.append(asyncio.create_task(_expirar_periodicamente(), name="expirar-comandos"))
    yield
    for tarefa in tarefas:
        tarefa.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarefa


settings = obter_settings()
if settings.producao and (problemas := settings.problemas_de_producao()):
    # Melhor não subir do que subir aberto: o erro aparece no "docker compose logs app".
    raise RuntimeError(
        "AMBIENTE=producao com configuração insegura no .env:\n- " + "\n- ".join(problemas)
    )

app = FastAPI(
    title="AgroEdge",
    description=(
        "API da plataforma AgroEdge. Autenticação por cookie de sessão (painel) ou por "
        "`Authorization: Bearer <token>` (chatbot e outros serviços). Datas em ISO 8601 UTC; "
        'campos `ts` em Unix (segundos). Erros: `{"erro": "codigo", "mensagem": "..."}`.'
    ),
    version="0.2.0",
    lifespan=lifespan,
    # As rotas da documentação ficam lá embaixo, para poder exigir login na produção.
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
    responses={401: {"model": Erro}, 404: {"model": Erro}},
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="agroedge_sessao",
    max_age=SESSAO_DIAS * 86400,
    same_site="lax",
    https_only=settings.producao,  # na VPS o cookie só trafega por HTTPS
)
origens = [o.strip() for o in settings.cors_origens.split(",") if o.strip()]
if origens:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origens,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------- erros no formato da seção 10


@app.exception_handler(ErroApp)
async def _erro_app(_request: Request, erro: ErroApp) -> JSONResponse:
    return JSONResponse({"erro": erro.codigo, "mensagem": erro.mensagem}, status_code=erro.status)


@app.exception_handler(RequestValidationError)
async def _erro_validacao(_request: Request, erro: RequestValidationError) -> JSONResponse:
    partes = []
    for e in erro.errors():
        campo = ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
        partes.append(f"{campo}: {e['msg']}" if campo else e["msg"])
    return JSONResponse(
        {"erro": "dados_invalidos", "mensagem": "Dados inválidos. " + "; ".join(partes)},
        status_code=422,
    )


@app.exception_handler(StarletteHTTPException)
async def _erro_http(_request: Request, erro: StarletteHTTPException) -> JSONResponse:
    codigos = {404: "nao_encontrado", 405: "metodo_nao_permitido", 401: "nao_autenticado"}
    return JSONResponse(
        {"erro": codigos.get(erro.status_code, "erro_http"), "mensagem": str(erro.detail)},
        status_code=erro.status_code,
    )


# ---------------------------------------------------------------- rotas

for modulo in (auth, fazendas, cultivos, dispositivos, stream, canais):
    app.include_router(modulo.rotas)


@app.get("/api/saude", tags=["sistema"])
async def saude() -> dict[str, object]:
    ingestor = getattr(app.state, "ingestor", None)
    return {"ok": True, "mqtt_conectado": bool(ingestor and ingestor.cliente)}


# ---------------------------------------------------------------- documentação da API


async def _acesso_docs(
    request: Request,
    sessao: Sessao,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> None:
    """No local, aberta. Na produção, só com login no painel (cookie) ou com token."""
    if settings.docs_protegidos:
        await usuario_atual(request, sessao, credenciais)


@app.get("/api/openapi.json", include_in_schema=False, dependencies=[Depends(_acesso_docs)])
async def openapi() -> JSONResponse:
    return JSONResponse(app.openapi())


@app.get("/api/docs", include_in_schema=False, dependencies=[Depends(_acesso_docs)])
async def docs() -> Response:
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="AgroEdge · API")


# ---------------------------------------------------------------- frontend (build do Vite)

PASTA_FRONTEND = Path(os.environ.get("FRONTEND_DIR", "../frontend/dist")).resolve()


@app.get("/{caminho:path}", include_in_schema=False)
async def frontend(caminho: str) -> Response:
    """Serve o painel: arquivo do build se existir; senão o index.html (rotas do React)."""
    if caminho == "api" or caminho.startswith("api/"):
        return JSONResponse(
            {"erro": "nao_encontrado", "mensagem": "Rota da API não encontrada."}, status_code=404
        )
    arquivo = (PASTA_FRONTEND / caminho).resolve()
    if caminho and arquivo.is_file() and arquivo.is_relative_to(PASTA_FRONTEND):
        # Arquivos com hash no nome (assets/) podem ficar em cache para sempre.
        cache = "public, max-age=31536000, immutable" if caminho.startswith("assets/") else None
        return FileResponse(arquivo, headers={"Cache-Control": cache} if cache else None)
    indice = PASTA_FRONTEND / "index.html"
    if not indice.is_file():
        return JSONResponse(
            {"erro": "sem_frontend", "mensagem": "Build do frontend não encontrado."},
            status_code=404,
        )
    return FileResponse(indice, headers={"Cache-Control": "no-cache"})
