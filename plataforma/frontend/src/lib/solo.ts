/** Presets de solo (apêndice B) e TAW/RAW só para exibir (a placa faz o cálculo de verdade). */
import type { TexturaSolo } from "@/api/tipos";

export const PRESETS_SOLO: Record<Exclude<TexturaSolo, "avancado">, number> = {
  arenoso: 0.08,
  franco_arenoso: 0.11,
  argiloso: 0.16,
};

export const TAW_TREINO = [25, 140] as const;

export function aguaDisponivel(textura: TexturaSolo, digitada: number | null | undefined): number {
  return textura === "avancado" ? (digitada ?? 0.11) : PRESETS_SOLO[textura];
}

export function calcularTawRaw(
  aguaDisp: number,
  raizM: number,
  p: number,
): { taw: number; raw: number; foraDaFaixa: boolean } {
  const taw = 1000 * aguaDisp * raizM;
  return { taw, raw: p * taw, foraDaFaixa: taw < TAW_TREINO[0] || taw > TAW_TREINO[1] };
}
