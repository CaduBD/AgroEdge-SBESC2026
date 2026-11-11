/** Períodos do Histórico: chips 7 dias, 30 dias, ciclo atual e personalizado (datas locais). */
import { TZDate } from "@date-fns/tz";
import { addDays, differenceInCalendarDays, format, parseISO } from "date-fns";

import { FUSO } from "./formatar";

export type TipoPeriodo = "7d" | "30d" | "ciclo" | "personalizado";

export interface Periodo {
  tipo: TipoPeriodo;
  /** AAAA-MM-DD (dia local, incluído) */
  de: string;
  /** AAAA-MM-DD (dia local, incluído) */
  ate: string;
}

export function hojeLocal(agora: Date = new Date()): string {
  return format(new TZDate(agora, FUSO), "yyyy-MM-dd");
}

function menosDias(dia: string, n: number): string {
  return format(addDays(parseISO(dia), -n), "yyyy-MM-dd");
}

/** Resolve o período a partir dos parâmetros da URL. */
export function resolverPeriodo(
  tipo: string | null,
  de: string | null,
  ate: string | null,
  dataReferencia: string | undefined,
  agora: Date = new Date(),
): Periodo {
  const hoje = hojeLocal(agora);
  const valida = (d: string | null) => !!d && /^\d{4}-\d{2}-\d{2}$/.test(d);
  if (tipo === "personalizado" && valida(de) && valida(ate) && de! <= ate!) {
    return { tipo, de: de!, ate: ate! };
  }
  if (tipo === "30d") return { tipo, de: menosDias(hoje, 29), ate: hoje };
  if (tipo === "ciclo" && dataReferencia) {
    const inicio = dataReferencia <= hoje ? dataReferencia : hoje;
    return { tipo, de: inicio, ate: hoje };
  }
  return { tipo: "7d", de: menosDias(hoje, 6), ate: hoje };
}

export function diasNoPeriodo(p: Periodo): number {
  return differenceInCalendarDays(parseISO(p.ate), parseISO(p.de)) + 1;
}

/** Início do dia local `de` e início do dia seguinte a `ate`, em Unix (para o eixo X). */
export function limitesUnix(p: Periodo): [number, number] {
  const inicio = new TZDate(`${p.de}T00:00:00`, FUSO);
  const fim = addDays(new TZDate(`${p.ate}T00:00:00`, FUSO), 1);
  return [Math.floor(inicio.getTime() / 1000), Math.floor(fim.getTime() / 1000)];
}
