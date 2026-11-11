import { describe, expect, it } from "vitest";

import { aguaDisponivel, calcularTawRaw } from "./solo";

describe("solo", () => {
  it("presets do apêndice B", () => {
    expect(aguaDisponivel("arenoso", 0.15)).toBe(0.08);
    expect(aguaDisponivel("franco_arenoso", null)).toBe(0.11);
    expect(aguaDisponivel("argiloso", null)).toBe(0.16);
    expect(aguaDisponivel("avancado", 0.15)).toBe(0.15);
  });
  it("TAW = 1000 × água × raiz; RAW = p × TAW", () => {
    const r = calcularTawRaw(0.11, 0.6, 0.5);
    expect(r.taw).toBeCloseTo(66);
    expect(r.raw).toBeCloseTo(33);
    expect(r.foraDaFaixa).toBe(false);
  });
  it("avisa fora da faixa de treino (25 a 140 mm)", () => {
    expect(calcularTawRaw(0.06, 0.4, 0.5).foraDaFaixa).toBe(true); // 24 mm
    expect(calcularTawRaw(0.18, 0.8, 0.5).foraDaFaixa).toBe(true); // 144 mm
  });
});
