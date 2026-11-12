"""Configuração do bot, lida das variáveis de ambiente (ou do arquivo chatbot/.env)."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

TIPOS_DE_ALERTA = {"diario", "status", "irrigacao"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Plataforma (CHATBOT.md, seção 1)
    agroedge_api_url: str = "http://localhost:8000"
    agroedge_token: str = ""

    # Telegram
    telegram_bot_token: str = ""
    # Proxy HTTP(S) para falar com o Telegram, se a rede exigir (p.ex. a da universidade)
    telegram_proxy: str = ""
    # Quem pode usar o bot fica na plataforma: cada produtor conecta a conversa pelo QR code
    # do painel (Conta → Telegram). Não há mais lista de chats aqui.

    # Alertas automáticos enviados pelo SSE
    bot_alertas: Annotated[set[str], NoDecode] = {"diario", "status", "irrigacao"}

    # Onde o bot guarda o que precisa lembrar entre reinícios (cultivo escolhido, alertas)
    bot_arquivo_estado: str = "estado_bot.json"

    # Fuso de exibição (a API manda tudo em UTC)
    bot_fuso: str = "America/Bahia"

    @field_validator("bot_alertas", mode="before")
    @classmethod
    def _lista(cls, valor: object) -> object:
        if isinstance(valor, str):
            return {item.strip() for item in valor.split(",") if item.strip()}
        return valor

    @field_validator("bot_alertas")
    @classmethod
    def _alertas_validos(cls, valor: set[str]) -> set[str]:
        invalidos = valor - TIPOS_DE_ALERTA
        if invalidos:
            raise ValueError(
                f"BOT_ALERTAS aceita {sorted(TIPOS_DE_ALERTA)}; inválidos: {sorted(invalidos)}"
            )
        return valor

    @field_validator("agroedge_api_url")
    @classmethod
    def _sem_barra_final(cls, valor: str) -> str:
        return valor.rstrip("/")


@lru_cache
def obter_settings() -> Settings:
    return Settings()
