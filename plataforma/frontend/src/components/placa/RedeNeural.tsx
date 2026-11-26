import { useMemo } from "react";

import { N_CLASSES, N_ENTRADAS, N_OCULTA, W1, W2 } from "@/lib/pesosV31";

const COR_CLASSE = ["var(--estado-adequado)", "var(--estado-moderado)", "var(--estado-critico)"];
const ROTULO = ["Adequado", "Moderado", "Crítico"];

const L = 340;
const A = 250;
const X = [34, 178, 290];
const yEntrada = (i: number) => 12 + (i * (A - 24)) / (N_ENTRADAS - 1);
const yOculta = (j: number) => 22 + (j * (A - 44)) / (N_OCULTA - 1);
const ySaida = (k: number) => A / 2 + (k - 1) * 58;

/**
 * Desenho da MLP 45 → 32 → 3 com os pesos reais do classificador v3.1.
 * As ligações mostradas são as mais fortes; em destaque, os neurônios ocultos que mais pesam
 * na classe que a placa escolheu (pesos W2 positivos). As entradas do dia não vêm da placa,
 * então nenhuma ativação é inventada aqui.
 */
export function RedeNeural({ classe }: { classe: number | null }) {
  const acesa = true;
  const { lig1, lig2, destaque } = useMemo(() => {
    const max1 = Math.max(...W1.map(Math.abs));
    const corte = [...W1].map(Math.abs).sort((a, b) => b - a)[140];
    const lig1 = [] as { i: number; j: number; w: number; f: number }[];
    for (let i = 0; i < N_ENTRADAS; i++)
      for (let j = 0; j < N_OCULTA; j++) {
        const w = W1[i * N_OCULTA + j];
        if (Math.abs(w) >= corte) lig1.push({ i, j, w, f: Math.abs(w) / max1 });
      }
    const max2 = Math.max(...W2.map(Math.abs));
    const lig2 = [] as { j: number; k: number; w: number; f: number }[];
    for (let j = 0; j < N_OCULTA; j++)
      for (let k = 0; k < N_CLASSES; k++) {
        const w = W2[j * N_CLASSES + k];
        lig2.push({ j, k, w, f: Math.abs(w) / max2 });
      }
    const destaque = new Set<number>();
    if (classe === 0 || classe === 1 || classe === 2) {
      Array.from({ length: N_OCULTA }, (_, j) => ({ j, w: W2[j * N_CLASSES + classe] }))
        .filter((x) => x.w > 0)
        .sort((a, b) => b.w - a.w)
        .slice(0, 8)
        .forEach((x) => destaque.add(x.j));
    }
    return { lig1, lig2, destaque };
  }, [classe]);

  const cor =
    classe != null && classe >= 0 && classe <= 2 ? COR_CLASSE[classe] : "var(--muted-foreground)";

  return (
    <svg
      viewBox={`0 0 ${L} ${A}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Rede neural 45 entradas, 32 neurônios ocultos e 3 classes; classe do dia: ${
        classe != null ? ROTULO[classe] : "sem classe"
      }`}
    >
      {lig1.map(({ i, j, w, f }) => (
        <line
          key={`a${i}-${j}`}
          x1={X[0]}
          y1={yEntrada(i)}
          x2={X[1]}
          y2={yOculta(j)}
          stroke={w > 0 ? "var(--primary)" : "var(--muted-foreground)"}
          strokeWidth={0.4 + f * 0.9}
          opacity={acesa && destaque.has(j) ? 0.15 + f * 0.6 : 0.06 + f * 0.18}
        />
      ))}
      {lig2.map(({ j, k, w, f }) => {
        const ativa = acesa && destaque.has(j) && k === classe;
        return (
          <line
            key={`b${j}-${k}`}
            x1={X[1]}
            y1={yOculta(j)}
            x2={X[2]}
            y2={ySaida(k)}
            stroke={ativa ? cor : w > 0 ? "var(--primary)" : "var(--muted-foreground)"}
            strokeWidth={ativa ? 1.2 + f * 1.4 : 0.4 + f * 0.6}
            opacity={ativa ? 0.85 : 0.05 + f * 0.15}
            className={ativa ? "pulso-ligacao" : undefined}
          />
        );
      })}
      {Array.from({ length: N_ENTRADAS }, (_, i) => (
        <circle
          key={`e${i}`}
          cx={X[0]}
          cy={yEntrada(i)}
          r={1.9}
          fill="var(--muted-foreground)"
          opacity={0.7}
        />
      ))}
      {Array.from({ length: N_OCULTA }, (_, j) => {
        const on = acesa && destaque.has(j);
        return (
          <circle
            key={`o${j}`}
            cx={X[1]}
            cy={yOculta(j)}
            r={on ? 3.6 : 2.6}
            fill={on ? cor : "var(--card)"}
            stroke={on ? cor : "var(--muted-foreground)"}
            strokeWidth={1}
          />
        );
      })}
      {[0, 1, 2].map((k) => {
        const on = acesa && k === classe;
        return (
          <g key={`s${k}`}>
            {on && (
              <circle
                cx={X[2]}
                cy={ySaida(k)}
                r={15}
                fill={COR_CLASSE[k]}
                opacity={0.18}
                className="brilho-saida"
              />
            )}
            <circle
              cx={X[2]}
              cy={ySaida(k)}
              r={9}
              fill={on ? COR_CLASSE[k] : "var(--card)"}
              stroke={COR_CLASSE[k]}
              strokeWidth={1.6}
              opacity={acesa && !on ? 0.45 : 1}
            />
            <text
              x={X[2] + 2}
              y={ySaida(k) + 31}
              textAnchor="middle"
              fontSize={9.5}
              fontWeight={on ? 700 : 500}
              fill={on ? COR_CLASSE[k] : "var(--muted-foreground)"}
            >
              {ROTULO[k]}
            </text>
          </g>
        );
      })}
      <text x={X[0]} y={A - 1} textAnchor="middle" fontSize={9} fill="var(--muted-foreground)">
        45 entradas
      </text>
      <text x={X[1]} y={A - 4} textAnchor="middle" fontSize={9} fill="var(--muted-foreground)">
        32 ocultos
      </text>
    </svg>
  );
}
