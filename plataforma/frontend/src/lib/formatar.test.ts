import { describe, expect, it } from "vitest";

import {
  celsius,
  diaHora,
  diaMesDeData,
  duracao,
  ha,
  hora,
  litros,
  mm,
  numero,
  radiacao,
} from "./formatar";

describe("números em pt-BR", () => {
  it("usa vírgula decimal e ponto de milhar", () => {
    expect(numero(6.1)).toBe("6,1");
    expect(numero(0.65, 2)).toBe("0,65");
    expect(litros(1250)).toBe("1.250 L");
  });
  it("unidades da seção 12.1", () => {
    expect(mm(6.1)).toBe("6,1 mm");
    expect(celsius(31.4)).toBe("31,4 °C");
    expect(radiacao(812)).toBe("812 W/m²");
  });
  it("valor ausente vira travessão", () => {
    expect(mm(null)).toBe("—");
    expect(numero(undefined)).toBe("—");
  });
});

describe("datas no fuso America/Bahia (UTC−3)", () => {
  it("converte UTC para a hora local", () => {
    expect(hora("2026-11-10T13:15:00Z")).toBe("10h15");
    expect(hora(1762437600)).toBe("11h00"); // 2025-11-06 14:00 UTC
    expect(diaHora("2026-11-10T03:00:00Z")).toBe("10/11 às 00h00");
  });
  it("data local AAAA-MM-DD não sofre conversão de fuso", () => {
    expect(diaMesDeData("2026-11-10")).toBe("10/11");
  });
  it("tempo relativo e duração", () => {
    const agora = new Date("2026-11-10T15:00:00Z");
    expect(ha("2026-11-10T13:00:00Z", agora)).toBe("há 2 h");
    expect(ha("2026-11-10T14:55:00Z", agora)).toBe("há 5 min");
    expect(duracao(new Date("2026-11-10T14:00:00Z"), new Date("2026-11-10T15:05:00Z"))).toBe(
      "1 h 05 min",
    );
  });
});
