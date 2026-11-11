import { numero } from "@/lib/formatar";

export interface Variavel {
  chave: string;
  rotulo: string;
  unidade: string;
  casas: number;
  cor: string;
  tipo: "linha" | "barra";
  /** Diagnóstico da placa (bateria, sinal), fora do padrão */
  diagnostico?: boolean;
}

export const VARIAVEIS: Variavel[] = [
  {
    chave: "temp_c",
    rotulo: "Temperatura",
    unidade: "°C",
    casas: 1,
    cor: "var(--estado-critico)",
    tipo: "linha",
  },
  {
    chave: "ur_pct",
    rotulo: "Umidade",
    unidade: "%",
    casas: 0,
    cor: "var(--sincronizando)",
    tipo: "linha",
  },
  {
    chave: "vento_ms",
    rotulo: "Vento",
    unidade: "m/s",
    casas: 1,
    cor: "var(--etc)",
    tipo: "linha",
  },
  {
    chave: "rad_wm2",
    rotulo: "Radiação",
    unidade: "W/m²",
    casas: 0,
    cor: "var(--estado-moderado)",
    tipo: "linha",
  },
  {
    chave: "chuva_mm",
    rotulo: "Chuva",
    unidade: "mm",
    casas: 1,
    cor: "var(--chuva)",
    tipo: "barra",
  },
  {
    chave: "bat_v",
    rotulo: "Bateria",
    unidade: "V",
    casas: 2,
    cor: "var(--sem-contato)",
    tipo: "linha",
    diagnostico: true,
  },
  {
    chave: "rssi",
    rotulo: "Sinal Wi-Fi",
    unidade: "dBm",
    casas: 0,
    cor: "var(--sem-contato)",
    tipo: "linha",
    diagnostico: true,
  },
];

export const PADRAO = ["temp_c", "ur_pct", "rad_wm2", "chuva_mm"];

export const variavel = (chave: string) => VARIAVEIS.find((v) => v.chave === chave)!;

export function formatarVariavel(chave: string, valor: number | null | undefined): string {
  if (valor == null) return "—";
  const v = variavel(chave);
  return `${numero(valor, v.casas)} ${v.unidade}`;
}
