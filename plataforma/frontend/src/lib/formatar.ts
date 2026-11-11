/**
 * Formatação no padrão brasileiro e no fuso de Petrolina (seção 12.1).
 * O backend manda datas em UTC (ISO com Z) e `ts` em Unix; a conversão acontece só aqui.
 */
import { TZDate } from "@date-fns/tz";
import { differenceInMinutes, format, formatDistanceStrict } from "date-fns";
import { ptBR } from "date-fns/locale";

export const FUSO = "America/Bahia";

const sem = "—";

/** 6,1 · 1.250 · 0,65 */
export function numero(valor: number | null | undefined, casas = 1): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return sem;
  return valor.toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}

export const mm = (v: number | null | undefined, casas = 1) =>
  v == null ? sem : `${numero(v, casas)} mm`;
export const celsius = (v: number | null | undefined) => (v == null ? sem : `${numero(v)} °C`);
export const porcento = (v: number | null | undefined) => (v == null ? sem : `${numero(v, 0)}%`);
export const vento = (v: number | null | undefined) => (v == null ? sem : `${numero(v)} m/s`);
export const radiacao = (v: number | null | undefined) =>
  v == null ? sem : `${numero(v, 0)} W/m²`;
export const litros = (v: number | null | undefined) => (v == null ? sem : `${numero(v, 0)} L`);
export const minutos = (v: number | null | undefined) => (v == null ? sem : `${numero(v, 0)} min`);

/** Converte ISO (UTC) ou Unix (s) para uma data no fuso de exibição. */
export function noFuso(valor: string | number | Date): TZDate {
  const data =
    typeof valor === "number"
      ? new Date(valor * 1000)
      : valor instanceof Date
        ? valor
        : new Date(valor);
  return new TZDate(data, FUSO);
}

/** 10h15 */
export function hora(valor: string | number | null | undefined): string {
  if (valor == null) return sem;
  return format(noFuso(valor), "HH'h'mm");
}

/** 10/11 */
export function diaMes(valor: string | number | Date | null | undefined): string {
  if (valor == null) return sem;
  return format(noFuso(valor), "dd/MM");
}

/** 10/11/2026 */
export function dataCompleta(valor: string | number | Date | null | undefined): string {
  if (valor == null) return sem;
  return format(noFuso(valor), "dd/MM/yyyy");
}

/** 10/11 às 14h30 */
export function diaHora(valor: string | number | null | undefined): string {
  if (valor == null) return sem;
  return format(noFuso(valor), "dd/MM 'às' HH'h'mm");
}

/** Data local AAAA-MM-DD (vinda do backend, sem fuso) → 10/11 */
export function diaMesDeData(iso: string | null | undefined): string {
  if (!iso) return sem;
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

/** Dia da semana curto de uma data local AAAA-MM-DD: "seg" */
export function diaSemana(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return format(new Date(a, m - 1, d), "EEEEEE", { locale: ptBR });
}

/** "há 2 h", "há 5 min" */
export function ha(valor: string | number | null | undefined, agora: Date = new Date()): string {
  if (valor == null) return sem;
  const data = typeof valor === "number" ? new Date(valor * 1000) : new Date(valor);
  if (differenceInMinutes(agora, data) < 1) return "agora há pouco";
  return `há ${formatDistanceStrict(data, agora, { locale: ptBR })
    .replace(" minutos", " min")
    .replace(" minuto", " min")
    .replace(" horas", " h")
    .replace(" hora", " h")}`;
}

/** Duração em minutos inteiros entre dois instantes: "12 min", "1 h 05 min" */
export function duracao(inicio: Date, fim: Date): string {
  const total = Math.max(0, differenceInMinutes(fim, inicio));
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${h} h ${String(m).padStart(2, "0")} min`;
}
