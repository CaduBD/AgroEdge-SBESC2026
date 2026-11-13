import { describe, expect, it } from "vitest";

import { avisarUmaVez, idToastConfig } from "./toasts";

describe("avisos que chegam por dois caminhos", () => {
  it("o mesmo aviso sai uma vez só", () => {
    const id = idToastConfig(4, 3);
    let n = 0;
    avisarUmaVez(id, () => n++); // evento do SSE
    avisarUmaVez(id, () => n++); // tela viu a mudança
    expect(n).toBe(1);
  });
  it("versões diferentes são avisos diferentes", () => {
    let n = 0;
    avisarUmaVez(idToastConfig(4, 4), () => n++);
    avisarUmaVez(idToastConfig(4, 5), () => n++);
    expect(n).toBe(2);
  });
});
