"""Entradas e saídas da API (seção 10). Tudo tipado para o OpenAPI em /api/docs ficar completo.

Datas e horas saem em ISO 8601 UTC com `Z`; campos `ts` saem em Unix (segundos).
"""

from datetime import UTC, date, datetime, time
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
)

from app.models import (
    AcaoComando,
    Canal,
    EstadoComando,
    EstadoIrrigacao,
    FonteIrrigacao,
    InicioUso,
    OrigemIrrigacao,
    StatusMqtt,
    TexturaSolo,
)


class Saida(BaseModel):
    """Base das respostas: lê de objetos do banco e escreve datas em UTC com Z."""

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", mode="wrap")
    def _datas_em_utc(self, valor: Any, seguinte: SerializerFunctionWrapHandler) -> Any:
        if isinstance(valor, datetime):
            if valor.tzinfo is None:
                valor = valor.replace(tzinfo=UTC)
            return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return seguinte(valor)


class Erro(BaseModel):
    erro: str = Field(examples=["nao_encontrado"])
    mensagem: str = Field(examples=["Cultivo não encontrado."])


class Ok(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------- auth


class LoginEntrada(BaseModel):
    email: str = Field(examples=["equipe@agroedge.local"])
    senha: str


class UsuarioSaida(Saida):
    id: int
    nome: str
    email: str


class TrocaSenhaEntrada(BaseModel):
    senha_atual: str
    senha_nova: str = Field(min_length=8)


# ---------------------------------------------------------------- catálogo


class FaseCultura(BaseModel):
    chave: str
    nome: str
    dias: int
    kc: float


class Cultura(BaseModel):
    chave: str = Field(examples=["manga_tommy_atkins"])
    nome: str
    referencia: Literal["poda", "floracao"]
    ciclo_dias: int
    p: float
    raiz_m: float
    fases: list[FaseCultura] | None


# ---------------------------------------------------------------- fazendas


class FazendaEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=100, examples=["Fazenda Boa Vista"])
    municipio: str | None = Field(default=None, examples=["Petrolina - PE"])
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class FazendaEdicao(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=100)
    municipio: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class FazendaSaida(Saida):
    id: int
    nome: str
    municipio: str | None
    latitude: float | None
    longitude: float | None
    criado_em: datetime
    n_cultivos: int = 0


# ---------------------------------------------------------------- cultivos


class CultivoEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=100, examples=["Pomar 2 · Tommy"])
    cultura: str = Field(examples=["manga_tommy_atkins"])
    data_referencia: date = Field(description="Poda (uva) ou início da floração (manga)")
    textura_solo: TexturaSolo = TexturaSolo.franco_arenoso
    agua_disp: float | None = Field(
        default=None, ge=0.06, le=0.18, description="m³/m³; só vale na textura 'avancado'"
    )
    raiz_m: float | None = Field(
        default=None, ge=0.4, le=0.8, description="Só na textura 'avancado'; nulo = padrão"
    )
    eficiencia: float = Field(default=0.9, ge=0.5, le=0.95)
    area_m2: float = Field(gt=0, description="Área por planta", examples=[40.0])
    vazao_l_h: float = Field(gt=0, description="Vazão dos emissores de uma planta", examples=[64.0])
    n_plantas: int | None = Field(default=None, gt=0)
    fonte_irrigacao: FonteIrrigacao = FonteIrrigacao.tempo
    inicio_uso: InicioUso = InicioUso.meio
    irrigacao_automatica: bool = True
    hora_irrigacao: time = Field(default=time(5, 0), examples=["05:00"])


class CultivoEdicao(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=100)
    cultura: str | None = None
    data_referencia: date | None = None
    textura_solo: TexturaSolo | None = None
    agua_disp: float | None = Field(default=None, ge=0.06, le=0.18)
    raiz_m: float | None = Field(default=None, ge=0.4, le=0.8)
    eficiencia: float | None = Field(default=None, ge=0.5, le=0.95)
    area_m2: float | None = Field(default=None, gt=0)
    vazao_l_h: float | None = Field(default=None, gt=0)
    n_plantas: int | None = Field(default=None, gt=0)
    fonte_irrigacao: FonteIrrigacao | None = None
    inicio_uso: InicioUso | None = None
    irrigacao_automatica: bool | None = None
    hora_irrigacao: time | None = None


class PodaEntrada(BaseModel):
    data: date = Field(description="Nova data de referência (poda ou floração)")


class ConfiguracaoPlaca(Saida):
    """Estado da configuração na placa instalada: 'aguardando' até a placa confirmar."""

    serial: str
    instalacao_id: int
    cfg_v: int
    cfg_v_aplicada: int | None
    aplicada: bool


class CultivoSaida(Saida):
    id: int
    fazenda_id: int
    nome: str
    cultura: str
    data_referencia: date
    textura_solo: TexturaSolo
    agua_disp: float
    raiz_m: float | None
    eficiencia: float
    area_m2: float
    vazao_l_h: float
    n_plantas: int | None
    fonte_irrigacao: FonteIrrigacao
    inicio_uso: InicioUso
    irrigacao_automatica: bool
    hora_irrigacao: time
    arquivado: bool
    exemplo: bool
    criado_em: datetime
    atualizado_em: datetime
    taw_mm: float
    raw_mm: float
    dia_do_ciclo: int
    ultima_classe: int | None = None
    configuracao: ConfiguracaoPlaca | None = None
    avisos: list[str] = []

    @field_serializer("hora_irrigacao")
    def _hora(self, valor: time) -> str:
        return valor.strftime("%H:%M")


# ---------------------------------------------------------------- dispositivos


class InstalarEntrada(BaseModel):
    cultivo_id: int
    inicio: datetime | None = Field(
        default=None, description="Padrão: agora. No passado, reatribui as leituras desde então."
    )


class InstalacaoSaida(Saida):
    id: int
    serial: str
    cultivo_id: int
    cultivo_nome: str
    inicio: datetime
    fim: datetime | None
    cfg_v: int
    cfg_v_aplicada: int | None
    config_publicada: dict[str, Any] | None = None


EstadoPill = Literal["ao_vivo", "atrasado", "sem_contato", "sincronizando"]


class DispositivoSaida(Saida):
    serial: str
    apelido: str | None
    intervalo_telemetria_min: int
    status: EstadoPill
    status_mqtt: StatusMqtt
    sincronizando: int
    ultimo_contato: datetime | None
    ultima_telemetria: datetime | None
    ultimo_seq: int | None
    bat_v: float | None
    rssi: int | None
    buf: int | None
    instalacao: InstalacaoSaida | None


class MensagemRejeitadaSaida(Saida):
    id: int
    topico: str
    payload: str
    motivo: str
    recebido_em: datetime


class ConexaoPlaca(BaseModel):
    """Valores para o config_local.py da placa (a senha não é guardada no servidor)."""

    mqtt_host: str
    mqtt_porta: int
    mqtt_usuario: str


class DispositivoDetalhe(DispositivoSaida):
    leituras_sem_cultivo: int
    rejeitadas: list[MensagemRejeitadaSaida]
    conexao: ConexaoPlaca


class ComandoEntrada(BaseModel):
    acao: AcaoComando
    minutos: float | None = Field(default=None, description="Obrigatório para 'abrir' (1 a 120)")


class ComandoSaida(Saida):
    id: str
    acao: AcaoComando
    minutos: float | None
    criado_em: datetime
    valido_ate: datetime
    estado: EstadoComando
    resultado: str | None
    respondido_em: datetime | None


# ---------------------------------------------------------------- dados


class LeituraSaida(Saida):
    ts: int
    seq: int
    temp_c: float | None
    ur_pct: float | None
    vento_ms: float | None
    rad_wm2: float | None
    chuva_mm: float | None
    bat_v: float | None
    rssi: int | None
    buf: int | None
    cfg_v: int | None
    recebido_em: datetime


class DiarioSaida(Saida):
    ts: int
    data: date
    cultura: str | None
    dap: int | None
    fase: str | None
    kc: float | None
    cobertura: float | None
    tmax: float | None
    tmin: float | None
    ur: float | None
    u2: float | None
    rs: float | None
    chuva: float | None
    irrigacao: float | None
    et0: float | None
    etc: float | None
    taw: float | None
    deficit: float | None
    classe: int | None
    lamina_bruta: float | None
    minutos: float | None
    consumo_l_planta: float | None
    consumo_l_total: float | None
    aplicar_l_planta: float | None
    aplicar_l_total: float | None
    avisos: list[str]
    recebido_em: datetime


class IrrigacaoSaida(Saida):
    id: str
    ts_inicio: int
    ts_fim: int | None
    minutos: float | None
    mm: float | None
    origem: OrigemIrrigacao
    cmd_id: str | None
    estado: EstadoIrrigacao


class Lacuna(BaseModel):
    inicio: int = Field(description="ts da última leitura antes da lacuna")
    fim: int = Field(description="ts da primeira leitura depois da lacuna")


class SerieSaida(BaseModel):
    resolucao: Literal["bruta", "hora", "dia"]
    de: int
    ate: int
    variaveis: list[str]
    pontos: list[dict[str, float | int | None]] = Field(
        examples=[[{"ts": 1762437600, "temp_c": 31.4, "chuva_mm": 0.0}]]
    )
    lacunas: list[Lacuna]


# ---------------------------------------------------------------- resumo


class CultivoResumo(CultivoSaida):
    fazenda: FazendaSaida
    cultura_info: Cultura | None
    raiz_efetiva_m: float


class DispositivoResumo(Saida):
    serial: str
    apelido: str | None
    status: EstadoPill
    sincronizando: int
    ultima_telemetria: datetime | None
    ultimo_contato: datetime | None
    bat_v: float | None
    rssi: int | None
    instalacao_id: int
    cfg_v: int
    cfg_v_aplicada: int | None
    cfg_aplicada: bool


class Ciclo(BaseModel):
    dias: int = Field(description="Dias desde a data de referência")
    ciclo_dias: int
    fora_do_ciclo: bool
    fase: str | None
    fase_nome: str | None


class Valvula(Saida):
    aberta: bool
    em_andamento: IrrigacaoSaida | None
    ultima: IrrigacaoSaida | None
    proxima_prevista: datetime | None


class DiaResumo(BaseModel):
    data: date
    hoje: bool
    fechado: bool = Field(description="Já tem fechamento diário da placa")
    chuva: float | None
    irrigacao: float | None
    etc: float | None
    et0: float | None
    classe: int | None


class ResumoSaida(BaseModel):
    cultivo: CultivoResumo
    dispositivo: DispositivoResumo | None
    ultima_leitura: LeituraSaida | None
    ultimo_diario: DiarioSaida | None
    ciclo: Ciclo
    valvula: Valvula
    ultimos_7_dias: list[DiaResumo]


# ---------------------------------------------------------------- chatbot (vínculo de conversas)


class BotSaida(BaseModel):
    canal: Canal
    usuario_bot: str | None = Field(
        description="@ do bot (sem arroba); nulo enquanto o chatbot não foi ligado"
    )


class BotEntrada(BaseModel):
    usuario_bot: str = Field(
        min_length=5, max_length=64, pattern=r"^[A-Za-z0-9_]+$", examples=["agroedge_bot"]
    )


class CodigoSaida(Saida):
    codigo: str
    link: str = Field(description="Abre o bot no Telegram já com o código (o QR code leva aqui)")
    usuario_bot: str
    expira_em: datetime


class VinculoSaida(Saida):
    id: int
    canal: Canal
    nome: str | None
    alertas: bool
    criado_em: datetime
    ultimo_uso: datetime | None


class SituacaoCodigo(Saida):
    """O painel consulta enquanto mostra o QR code, para saber quando a conversa conectou."""

    expira_em: datetime
    usado_em: datetime | None
    vinculo: VinculoSaida | None


class VincularEntrada(BaseModel):
    codigo: str = Field(min_length=4, max_length=64)
    conversa_id: str = Field(min_length=1, max_length=64)
    nome: str | None = Field(default=None, max_length=100)


class ConversaSaida(Saida):
    """Uma conversa vinculada, como o chatbot a enxerga."""

    canal: Canal
    conversa_id: str
    usuario_id: int
    usuario_nome: str
    alertas: bool
    cultivo_id: int | None


class ConversaEdicao(BaseModel):
    alertas: bool | None = None
    cultivo_id: int | None = Field(default=None, description="0 limpa a escolha")
