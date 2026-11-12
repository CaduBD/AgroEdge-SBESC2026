"""Tabelas do banco (seção 8). Datas e horas sempre em UTC, sem fuso (naive)."""

from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Any

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column, Index, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def agora_utc() -> datetime:
    """Agora em UTC, sem fuso (é o formato guardado no banco)."""
    return datetime.now(UTC).replace(tzinfo=None)


def ts_para_datetime(ts: int) -> datetime:
    """Unix (s, UTC) → datetime UTC sem fuso."""
    return datetime.fromtimestamp(ts, UTC).replace(tzinfo=None)


def datetime_para_ts(dt: datetime) -> int:
    """datetime UTC sem fuso → Unix (s)."""
    return int(dt.replace(tzinfo=UTC).timestamp())


# ---------------------------------------------------------------- enums (apêndice C)


class TexturaSolo(StrEnum):
    arenoso = "arenoso"
    franco_arenoso = "franco_arenoso"
    argiloso = "argiloso"
    avancado = "avancado"


class FonteIrrigacao(StrEnum):
    sensor = "sensor"
    manual = "manual"
    tempo = "tempo"
    parcial = "parcial"
    nenhuma = "nenhuma"


class InicioUso(StrEnum):
    ciclo = "ciclo"
    apos_irr = "apos_irr"
    meio = "meio"


class StatusMqtt(StrEnum):
    online = "online"
    offline = "offline"
    desconhecido = "desconhecido"


class OrigemIrrigacao(StrEnum):
    automatica = "automatica"
    manual = "manual"


class EstadoIrrigacao(StrEnum):
    iniciada = "iniciada"
    concluida = "concluida"
    cancelada = "cancelada"
    interrompida = "interrompida"


class AcaoComando(StrEnum):
    abrir = "abrir"
    cancelar = "cancelar"


class EstadoComando(StrEnum):
    enviado = "enviado"
    executado = "executado"
    recusado = "recusado"
    expirado = "expirado"


# ---------------------------------------------------------------- tabelas


class EscopoToken(StrEnum):
    usuario = "usuario"
    chatbot = "chatbot"


class Canal(StrEnum):
    """Aplicativos de mensagem pelos quais o produtor fala com o chatbot."""

    telegram = "telegram"


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: int | None = Field(default=None, primary_key=True)
    nome: str
    email: str = Field(unique=True)
    senha_hash: str
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)


class TokenServico(SQLModel, table=True):
    """Token de acesso de serviços (chatbot). Guardado só em hash (seção 10.1)."""

    __tablename__ = "tokens_servico"

    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True)
    nome: str
    token_hash: str = Field(unique=True)
    # "usuario": age só como o próprio dono. "chatbot": também age em nome das conversas
    # vinculadas (cabeçalho X-Conversa) e recebe o SSE de todos os usuários.
    escopo: str = Field(default=EscopoToken.usuario, sa_column_kwargs={"server_default": "usuario"})
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)
    ultimo_uso: NaiveDatetime | None = None


class Fazenda(SQLModel, table=True):
    __tablename__ = "fazendas"
    __table_args__ = (UniqueConstraint("usuario_id", "nome", name="uq_fazenda_usuario_nome"),)

    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True)
    nome: str
    municipio: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)


class Cultivo(SQLModel, table=True):
    __tablename__ = "cultivos"

    id: int | None = Field(default=None, primary_key=True)
    fazenda_id: int = Field(foreign_key="fazendas.id", index=True)
    nome: str
    cultura: str
    data_referencia: date
    textura_solo: TexturaSolo = TexturaSolo.franco_arenoso
    agua_disp: float = 0.11
    raiz_m: float | None = None
    eficiencia: float = 0.9
    area_m2: float
    vazao_l_h: float
    n_plantas: int | None = None
    fonte_irrigacao: FonteIrrigacao = FonteIrrigacao.tempo
    inicio_uso: InicioUso = InicioUso.meio
    irrigacao_automatica: bool = True
    hora_irrigacao: time = time(5, 0)
    arquivado: bool = False
    exemplo: bool = False  # criado pelo seed
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)
    atualizado_em: NaiveDatetime = Field(default_factory=agora_utc)


class Dispositivo(SQLModel, table=True):
    __tablename__ = "dispositivos"

    id: int | None = Field(default=None, primary_key=True)
    serial: str = Field(unique=True)
    # Dono da placa. Nulo = placa ainda não ativada (ativação por QR code é futura).
    usuario_id: int | None = Field(default=None, foreign_key="usuarios.id", index=True)
    apelido: str | None = None
    intervalo_telemetria_min: int = 15
    status_mqtt: StatusMqtt = StatusMqtt.desconhecido
    ultimo_contato: NaiveDatetime | None = None
    ultimo_seq: int | None = None
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)


class Instalacao(SQLModel, table=True):
    """Período em que uma placa ficou instalada num cultivo. fim nulo = ativa."""

    __tablename__ = "instalacoes"
    __table_args__ = (
        # No máximo uma instalação ativa por dispositivo.
        Index(
            "uq_instalacao_ativa",
            "dispositivo_id",
            unique=True,
            sqlite_where=text("fim IS NULL"),
            postgresql_where=text("fim IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    dispositivo_id: int = Field(foreign_key="dispositivos.id", index=True)
    cultivo_id: int = Field(foreign_key="cultivos.id", index=True)
    inicio: NaiveDatetime
    fim: NaiveDatetime | None = None
    cfg_v: int = 1
    cfg_v_aplicada: int | None = None
    config_publicada: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)


class Leitura(SQLModel, table=True):
    __tablename__ = "leituras"
    __table_args__ = (
        UniqueConstraint("dispositivo_id", "ts", name="uq_leitura_dispositivo_ts"),
        Index("ix_leituras_instalacao_ts", "instalacao_id", "ts"),
    )

    id: int | None = Field(default=None, primary_key=True)
    dispositivo_id: int = Field(foreign_key="dispositivos.id")
    instalacao_id: int | None = Field(default=None, foreign_key="instalacoes.id")
    ts: int
    seq: int
    temp_c: float | None = None
    ur_pct: float | None = None
    vento_ms: float | None = None
    rad_wm2: float | None = None
    chuva_mm: float | None = None
    bat_v: float | None = None
    rssi: int | None = None
    buf: int | None = None
    cfg_v: int | None = None
    recebido_em: NaiveDatetime = Field(default_factory=agora_utc)


class Diario(SQLModel, table=True):
    """Fechamento diário calculado na placa (payload `diario`)."""

    __tablename__ = "diarios"
    __table_args__ = (
        UniqueConstraint("dispositivo_id", "data", name="uq_diario_dispositivo_data"),
        Index("ix_diarios_instalacao_data", "instalacao_id", "data"),
    )

    id: int | None = Field(default=None, primary_key=True)
    dispositivo_id: int = Field(foreign_key="dispositivos.id")
    instalacao_id: int | None = Field(default=None, foreign_key="instalacoes.id")
    ts: int
    seq: int
    cfg_v: int | None = None
    data: date
    cultura: str | None = None
    dap: int | None = None
    fase: str | None = None
    kc: float | None = None
    cobertura: float | None = None
    tmax: float | None = None
    tmin: float | None = None
    ur: float | None = None
    u2: float | None = None
    rs: float | None = None
    chuva: float | None = None
    irrigacao: float | None = None
    et0: float | None = None
    etc: float | None = None
    taw: float | None = None
    deficit: float | None = None
    classe: int | None = None
    lamina_bruta: float | None = None
    minutos: float | None = None
    consumo_l_planta: float | None = None
    consumo_l_total: float | None = None
    aplicar_l_planta: float | None = None
    aplicar_l_total: float | None = None
    avisos: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    recebido_em: NaiveDatetime = Field(default_factory=agora_utc)


class Irrigacao(SQLModel, table=True):
    __tablename__ = "irrigacoes"
    __table_args__ = (Index("ix_irrigacoes_instalacao_ts", "instalacao_id", "ts_inicio"),)

    id: str = Field(primary_key=True)
    dispositivo_id: int = Field(foreign_key="dispositivos.id", index=True)
    instalacao_id: int | None = Field(default=None, foreign_key="instalacoes.id")
    ts_inicio: int
    ts_fim: int | None = None
    minutos: float | None = None
    mm: float | None = None
    origem: OrigemIrrigacao
    cmd_id: str | None = None
    estado: EstadoIrrigacao
    atualizado_em: NaiveDatetime = Field(default_factory=agora_utc)


class Comando(SQLModel, table=True):
    __tablename__ = "comandos"

    id: str = Field(primary_key=True)
    dispositivo_id: int = Field(foreign_key="dispositivos.id", index=True)
    usuario_id: int = Field(foreign_key="usuarios.id")
    acao: AcaoComando
    minutos: float | None = None
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)
    valido_ate: NaiveDatetime
    estado: EstadoComando = EstadoComando.enviado
    resultado: str | None = None
    respondido_em: NaiveDatetime | None = None


class MensagemRejeitada(SQLModel, table=True):
    """Mensagens MQTT descartadas, para diagnóstico na tela Dispositivo."""

    __tablename__ = "mensagens_rejeitadas"

    id: int | None = Field(default=None, primary_key=True)
    topico: str
    payload: str
    motivo: str
    recebido_em: NaiveDatetime = Field(default_factory=agora_utc, index=True)


# ---------------------------------------------------------------- chatbot (vínculo de conversas)


class BotCanal(SQLModel, table=True):
    """Bot que atende um canal. O chatbot se registra ao iniciar (é daqui que sai o link)."""

    __tablename__ = "bots_canal"

    canal: Canal = Field(primary_key=True)
    usuario_bot: str  # @ do bot, sem a arroba (ex.: agroedge_bot)
    atualizado_em: NaiveDatetime = Field(default_factory=agora_utc)


class VinculoCanal(SQLModel, table=True):
    """Conversa de um aplicativo de mensagem ligada a um usuário da plataforma."""

    __tablename__ = "vinculos_canal"
    __table_args__ = (UniqueConstraint("canal", "conversa_id", name="uq_vinculo_canal_conversa"),)

    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True)
    canal: Canal
    conversa_id: str  # chat id do Telegram (no WhatsApp seria o telefone)
    nome: str | None = None  # como a conversa aparece no app (ex.: "Carlos (@carlos)")
    alertas: bool = True
    cultivo_id: int | None = None  # cultivo escolhido na conversa
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)
    ultimo_uso: NaiveDatetime | None = None


class CodigoVinculo(SQLModel, table=True):
    """Código de uso único do QR code "Conectar Telegram" (vale poucos minutos)."""

    __tablename__ = "codigos_vinculo"

    codigo: str = Field(primary_key=True)
    usuario_id: int = Field(foreign_key="usuarios.id", index=True)
    canal: Canal
    criado_em: NaiveDatetime = Field(default_factory=agora_utc)
    expira_em: NaiveDatetime
    usado_em: NaiveDatetime | None = None
    vinculo_id: int | None = None  # conversa que usou o código (o painel mostra "conectado")
