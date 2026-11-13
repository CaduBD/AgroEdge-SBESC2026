"""Configuração da plataforma, lida das variáveis de ambiente (arquivo .env)."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores de exemplo do .env.example e padrões do código: em produção, nenhum deles vale.
_VALORES_DE_EXEMPLO = {
    "",
    "trocar-em-producao",
    "gere-um-valor-aleatorio-longo",
    "gere-um-token-aleatorio-longo",
    "gere-uma-senha",
    "gere-outra-senha",
    "troque-esta-senha",
}
SEGREDO_MINIMO = 32  # caracteres (o gerar_env.py cria 43)


class Settings(BaseSettings):
    # No Docker as variáveis vêm do env_file do compose; rodando local a partir de
    # backend/, o .env fica um nível acima (plataforma/.env).
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    # "local" (notebook, sem HTTPS) ou "producao" (VPS atrás do Caddy, com HTTPS).
    # Em produção: cookie só por HTTPS, segredos conferidos na partida e /api/docs com login.
    ambiente: Literal["local", "producao"] = "local"
    # /api/docs e /api/openapi.json: vazio = abertos no local e com login na produção.
    docs_publicos: bool | None = None

    # Limite de tentativas de login (por IP; por e-mail o limite é 4x maior)
    login_max_falhas: int = 5
    login_janela_min: int = 15

    # Login (usuário único criado no seed)
    admin_nome: str = "Equipe AgroEdge"
    admin_email: str = "equipe@agroedge.local"
    admin_senha: str = ""

    # Sessão e acesso por token
    session_secret: str = "trocar-em-producao"
    chatbot_token: str = ""
    cors_origens: str = ""

    # Banco
    database_url: str = "sqlite+aiosqlite:///./dados/agroedge.db"

    # Broker
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_usuario: str = "plataforma"
    mqtt_senha: str = ""
    mqtt_tls: bool = False
    mqtt_habilitado: bool = True  # desligado nos testes

    # Placa padrão (seed e simulador)
    dispositivo_serial: str = "agroedge-00001"
    dispositivo_senha: str = ""

    # Exibição
    broker_host_publico: str = "172.20.10.10"
    # Porta que a placa usa (na VPS, 8883 com TLS). Vazio = a mesma do backend (MQTT_PORT).
    broker_porta_publica: int | None = None
    broker_tls_publico: bool = False  # a placa conecta com TLS (na VPS, sim)
    tz_exibicao: str = "America/Bahia"

    @field_validator("docs_publicos", "broker_porta_publica", mode="before")
    @classmethod
    def _vazio_e_nenhum(cls, valor: object) -> object:
        """`DOCS_PUBLICOS=` (vazio, como no .env.example) quer dizer "automático"."""
        return None if isinstance(valor, str) and not valor.strip() else valor

    @property
    def producao(self) -> bool:
        return self.ambiente == "producao"

    @property
    def docs_protegidos(self) -> bool:
        return not self.docs_publicos if self.docs_publicos is not None else self.producao

    def problemas_de_producao(self) -> list[str]:
        """O que impede subir em produção (vazio = tudo certo). Só nomes, nunca os valores."""
        problemas = []
        curto = f"use um valor aleatório de {SEGREDO_MINIMO}+ caracteres"
        if self.session_secret in _VALORES_DE_EXEMPLO or len(self.session_secret) < SEGREDO_MINIMO:
            problemas.append(f"SESSION_SECRET: {curto}")
        if self.chatbot_token and (
            self.chatbot_token in _VALORES_DE_EXEMPLO or len(self.chatbot_token) < SEGREDO_MINIMO
        ):
            problemas.append(f"CHATBOT_TOKEN: {curto}")
        if self.mqtt_habilitado and self.mqtt_senha in _VALORES_DE_EXEMPLO:
            problemas.append("MQTT_SENHA: está vazia ou com o valor de exemplo")
        if self.admin_senha in _VALORES_DE_EXEMPLO - {""}:
            problemas.append("ADMIN_SENHA: está com o valor de exemplo")
        return problemas


@lru_cache
def obter_settings() -> Settings:
    return Settings()
