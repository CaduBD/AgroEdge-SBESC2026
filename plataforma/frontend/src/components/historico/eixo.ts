/** Eixo de tempo dos gráficos do Histórico: marcas à meia-noite local. */
import { TZDate } from "@date-fns/tz";
import { addDays, format } from "date-fns";

import { FUSO, noFuso } from "@/lib/formatar";

/** Marcas diárias (no máximo ~8), alinhadas à meia-noite de Petrolina. */
export function marcasDiarias(inicio: number, fim: number, maximo = 8): number[] {
  const dias = Math.max(1, Math.round((fim - inicio) / 86400));
  const passo = Math.max(1, Math.ceil(dias / maximo));
  const marcas: number[] = [];
  let dia = new TZDate(noFuso(inicio).setHours(0, 0, 0, 0), FUSO);
  while (dia.getTime() / 1000 <= fim) {
    marcas.push(Math.floor(dia.getTime() / 1000));
    dia = addDays(dia, passo);
  }
  return marcas;
}

export const rotuloDia = (ts: number) => format(noFuso(ts), "dd/MM");
export const rotuloDiaHora = (ts: number) => format(noFuso(ts), "dd/MM 'às' HH'h'mm");

/**
 * Insere pontos nulos no começo de cada lacuna para a linha "quebrar" ali,
 * em vez de ligar os dois lados como se houvesse dados.
 */
export function quebrarNasLacunas<T extends { ts: number }>(
  pontos: T[],
  lacunas: { inicio: number; fim: number }[],
  chaves: string[],
): (T | ({ ts: number } & Record<string, null>))[] {
  if (!lacunas.length) return pontos;
  const nulos = lacunas.map((l) => ({
    ts: l.inicio + 1,
    ...Object.fromEntries(chaves.map((k) => [k, null])),
  })) as ({ ts: number } & Record<string, null>)[];
  return [...pontos, ...nulos].sort((a, b) => a.ts - b.ts);
}
