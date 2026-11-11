/** Rótulos da tela para os enums (apêndice C) e cores semânticas. */

export type Classe = 0 | 1 | 2 | null;

export const CLASSE: Record<0 | 1 | 2, { rotulo: string; cor: string; fundo: string }> = {
  0: {
    rotulo: "Adequado",
    cor: "text-estado-adequado",
    fundo: "bg-estado-adequado/12 text-estado-adequado border-estado-adequado/30",
  },
  1: {
    rotulo: "Déficit moderado",
    cor: "text-estado-moderado",
    fundo: "bg-estado-moderado/12 text-estado-moderado border-estado-moderado/30",
  },
  2: {
    rotulo: "Déficit crítico",
    cor: "text-estado-critico",
    fundo: "bg-estado-critico/12 text-estado-critico border-estado-critico/30",
  },
};

export const SEM_CLASSE = {
  rotulo: "Sem classe",
  cor: "text-muted-foreground",
  fundo: "bg-muted text-muted-foreground border-border",
};

export function classeInfo(classe: number | null | undefined) {
  return classe === 0 || classe === 1 || classe === 2 ? CLASSE[classe] : SEM_CLASSE;
}

export const TEXTURA_SOLO: Record<string, string> = {
  arenoso: "Arenoso",
  franco_arenoso: "Franco-arenoso",
  argiloso: "Argiloso",
  avancado: "Avançado",
};

export const FONTE_IRRIGACAO: Record<string, string> = {
  sensor: "Sensor de vazão",
  manual: "Produtor informa a quantidade",
  tempo: "Tempo de válvula (placa)",
  parcial: "Registro de vez em quando",
  nenhuma: "Sem informação",
};

export const INICIO_USO: Record<string, string> = {
  ciclo: "No início do ciclo",
  apos_irr: "Logo após uma irrigação forte",
  meio: "No meio do ciclo",
};

export const ORIGEM_IRRIGACAO: Record<string, string> = {
  automatica: "Automática",
  manual: "Manual",
};

export const ESTADO_IRRIGACAO: Record<string, string> = {
  iniciada: "Em andamento",
  concluida: "Concluída",
  cancelada: "Cancelada",
  interrompida: "Interrompida",
};

export const ESTADO_COMANDO: Record<string, string> = {
  enviado: "Enviado",
  executado: "Executado",
  recusado: "Recusado",
  expirado: "Expirado",
};

export const RESULTADO_COMANDO: Record<string, string> = {
  executado: "Executado pela placa",
  recusado_vencido: "Recusado: chegou vencido",
  recusado_em_andamento: "Recusado: já havia uma irrigação em andamento",
  cancelado: "Cancelado",
  recusado_invalido: "Recusado: comando inválido",
};
