/** Tipos das respostas da API (espelham backend/app/schemas/api.py). */

export interface Usuario {
  id: number;
  nome: string;
  email: string;
}

export interface FaseCultura {
  chave: string;
  nome: string;
  dias: number;
  kc: number;
}

export interface Cultura {
  chave: string;
  nome: string;
  referencia: "poda" | "floracao";
  ciclo_dias: number;
  p: number;
  raiz_m: number;
  fases: FaseCultura[] | null;
}

export interface Fazenda {
  id: number;
  nome: string;
  municipio: string | null;
  latitude: number | null;
  longitude: number | null;
  criado_em: string;
  n_cultivos: number;
}

export interface ConfiguracaoPlaca {
  serial: string;
  instalacao_id: number;
  cfg_v: number;
  cfg_v_aplicada: number | null;
  aplicada: boolean;
}

export type TexturaSolo = "arenoso" | "franco_arenoso" | "argiloso" | "avancado";
export type FonteIrrigacao = "sensor" | "manual" | "tempo" | "parcial" | "nenhuma";
export type InicioUso = "ciclo" | "apos_irr" | "meio";

export interface Cultivo {
  id: number;
  fazenda_id: number;
  nome: string;
  cultura: string;
  data_referencia: string;
  textura_solo: TexturaSolo;
  agua_disp: number;
  raiz_m: number | null;
  eficiencia: number;
  area_m2: number;
  vazao_l_h: number;
  n_plantas: number | null;
  fonte_irrigacao: FonteIrrigacao;
  inicio_uso: InicioUso;
  irrigacao_automatica: boolean;
  hora_irrigacao: string;
  arquivado: boolean;
  exemplo: boolean;
  criado_em: string;
  atualizado_em: string;
  taw_mm: number;
  raw_mm: number;
  dia_do_ciclo: number;
  ultima_classe: number | null;
  configuracao: ConfiguracaoPlaca | null;
  avisos: string[];
}

export type EstadoPill = "ao_vivo" | "atrasado" | "sem_contato" | "sincronizando";

export interface Leitura {
  ts: number;
  seq: number;
  temp_c: number | null;
  ur_pct: number | null;
  vento_ms: number | null;
  rad_wm2: number | null;
  chuva_mm: number | null;
  bat_v: number | null;
  rssi: number | null;
  buf: number | null;
  cfg_v: number | null;
  recebido_em: string;
}

export interface Diario {
  ts: number;
  data: string;
  cultura: string | null;
  dap: number | null;
  fase: string | null;
  kc: number | null;
  cobertura: number | null;
  tmax: number | null;
  tmin: number | null;
  ur: number | null;
  u2: number | null;
  rs: number | null;
  chuva: number | null;
  irrigacao: number | null;
  et0: number | null;
  etc: number | null;
  taw: number | null;
  deficit: number | null;
  classe: number | null;
  lamina_bruta: number | null;
  minutos: number | null;
  consumo_l_planta: number | null;
  consumo_l_total: number | null;
  aplicar_l_planta: number | null;
  aplicar_l_total: number | null;
  avisos: string[];
  recebido_em: string;
}

export interface Irrigacao {
  id: string;
  ts_inicio: number;
  ts_fim: number | null;
  minutos: number | null;
  mm: number | null;
  origem: "automatica" | "manual";
  cmd_id: string | null;
  estado: "iniciada" | "concluida" | "cancelada" | "interrompida";
}

export interface DispositivoResumo {
  serial: string;
  apelido: string | null;
  status: EstadoPill;
  sincronizando: number;
  ultima_telemetria: string | null;
  ultimo_contato: string | null;
  bat_v: number | null;
  rssi: number | null;
  instalacao_id: number;
  cfg_v: number;
  cfg_v_aplicada: number | null;
  cfg_aplicada: boolean;
}

export interface Ciclo {
  dias: number;
  ciclo_dias: number;
  fora_do_ciclo: boolean;
  fase: string | null;
  fase_nome: string | null;
}

export interface Valvula {
  aberta: boolean;
  em_andamento: Irrigacao | null;
  ultima: Irrigacao | null;
  proxima_prevista: string | null;
}

export interface DiaResumo {
  data: string;
  hoje: boolean;
  fechado: boolean;
  chuva: number | null;
  irrigacao: number | null;
  etc: number | null;
  et0: number | null;
  classe: number | null;
}

export interface Resumo {
  cultivo: Cultivo & { fazenda: Fazenda; cultura_info: Cultura | null; raiz_efetiva_m: number };
  dispositivo: DispositivoResumo | null;
  ultima_leitura: Leitura | null;
  ultimo_diario: Diario | null;
  ciclo: Ciclo;
  valvula: Valvula;
  ultimos_7_dias: DiaResumo[];
}

export interface Comando {
  id: string;
  acao: "abrir" | "cancelar";
  minutos: number | null;
  criado_em: string;
  valido_ate: string;
  estado: "enviado" | "executado" | "recusado" | "expirado";
  resultado: string | null;
  respondido_em: string | null;
}

export interface Lacuna {
  inicio: number;
  fim: number;
}

export type Resolucao = "bruta" | "hora" | "dia";

export interface Serie {
  resolucao: Resolucao;
  de: number;
  ate: number;
  variaveis: string[];
  pontos: ({ ts: number } & Record<string, number | null>)[];
  lacunas: Lacuna[];
}

export interface Instalacao {
  id: number;
  serial: string;
  cultivo_id: number;
  cultivo_nome: string;
  inicio: string;
  fim: string | null;
  cfg_v: number;
  cfg_v_aplicada: number | null;
  config_publicada: Record<string, unknown> | null;
}

export interface Dispositivo {
  serial: string;
  apelido: string | null;
  intervalo_telemetria_min: number;
  status: EstadoPill;
  status_mqtt: "online" | "offline" | "desconhecido";
  sincronizando: number;
  ultimo_contato: string | null;
  ultima_telemetria: string | null;
  ultimo_seq: number | null;
  bat_v: number | null;
  rssi: number | null;
  buf: number | null;
  instalacao: Instalacao | null;
}

export interface MensagemRejeitada {
  id: number;
  topico: string;
  payload: string;
  motivo: string;
  recebido_em: string;
}

export interface DispositivoDetalhe extends Dispositivo {
  leituras_sem_cultivo: number;
  rejeitadas: MensagemRejeitada[];
  conexao: { mqtt_host: string; mqtt_porta: number; mqtt_usuario: string };
}

/** Corpo para criar/editar cultivo (POST/PATCH). */
export interface CultivoEntrada {
  nome: string;
  cultura: string;
  data_referencia: string;
  textura_solo: TexturaSolo;
  agua_disp?: number | null;
  raiz_m?: number | null;
  eficiencia: number;
  area_m2: number;
  vazao_l_h: number;
  n_plantas?: number | null;
  fonte_irrigacao: FonteIrrigacao;
  inicio_uso: InicioUso;
  irrigacao_automatica: boolean;
  hora_irrigacao: string;
}

// ---------------------------------------------------------------- chatbot

export interface BotCanal {
  canal: "telegram";
  usuario_bot: string | null;
}

export interface CodigoVinculo {
  codigo: string;
  link: string;
  usuario_bot: string;
  expira_em: string;
}

export interface VinculoCanal {
  id: number;
  canal: "telegram";
  nome: string | null;
  alertas: boolean;
  criado_em: string;
  ultimo_uso: string | null;
}

export interface SituacaoCodigo {
  expira_em: string;
  usado_em: string | null;
  vinculo: VinculoCanal | null;
}
