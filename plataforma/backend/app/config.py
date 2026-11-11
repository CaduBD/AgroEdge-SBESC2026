"""Configuração da plataforma, lida das variáveis de ambiente (arquivo .env)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # No Docker as variáveis vêm do env_file do compose; rodando local a partir de
    # backend/, o .env fica um nível acima (plataforma/.env).
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

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
    tz_exibicao: str = "America/Bahia"


@lru_cache
def obter_settings() -> Settings:
    return Settings()
