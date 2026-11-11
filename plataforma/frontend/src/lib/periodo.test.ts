import { describe, expect, it } from "vitest";

import { diasNoPeriodo, hojeLocal, limitesUnix, resolverPeriodo } from "./periodo";

// 11/11/2026 01:30 UTC = 10/11/2026 22:30 em Petrolina
const AGORA = new Date("2026-11-11T01:30:00Z");

describe("períodos do Histórico", () => {
  it("o dia de hoje é o dia local, não o UTC", () => {
    expect(hojeLocal(AGORA)).toBe("2026-11-10");
  });
  it("7 dias e 30 dias terminam hoje e incluem hoje", () => {
    const p7 = resolverPeriodo("7d", null, null, undefined, AGORA);
    expect(p7).toEqual({ tipo: "7d", de: "2026-11-04", ate: "2026-11-10" });
    expect(diasNoPeriodo(p7)).toBe(7);
    expect(diasNoPeriodo(resolverPeriodo("30d", null, null, undefined, AGORA))).toBe(30);
  });
  it("ciclo atual começa na data de referência", () => {
    expect(resolverPeriodo("ciclo", null, null, "2026-09-29", AGORA).de).toBe("2026-09-29");
  });
  it("personalizado inválido volta para 7 dias", () => {
    expect(
      resolverPeriodo("personalizado", "2026-11-10", "2026-11-01", undefined, AGORA).tipo,
    ).toBe("7d");
    expect(resolverPeriodo("personalizado", "2026-11-01", "2026-11-05", undefined, AGORA)).toEqual({
      tipo: "personalizado",
      de: "2026-11-01",
      ate: "2026-11-05",
    });
  });
  it("limites em Unix seguem a meia-noite local (UTC−3)", () => {
    const [ini, fim] = limitesUnix({ tipo: "personalizado", de: "2026-11-10", ate: "2026-11-10" });
    expect(new Date(ini * 1000).toISOString()).toBe("2026-11-10T03:00:00.000Z");
    expect(fim - ini).toBe(86400);
  });
});
