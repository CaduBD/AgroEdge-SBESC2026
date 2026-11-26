import { memo, useMemo } from "react";

import { N_CLASSES, N_ENTRADAS, N_OCULTA, W1, W2 } from "@/lib/pesosV31";

const COR_CLASSE = ["var(--estado-adequado)", "var(--estado-moderado)", "var(--estado-critico)"];
const ROTULO = ["Adequado", "Moderado", "Crítico"];

const L = 340;
const A = 250;
const X = [34, 178, 290];
const yEntrada = (i: number) => 12 + (i * (A - 24)) / (N_ENTRADAS - 1);
const yOculta = (j: number) => 22 + (j * (A - 44)) / (N_OCULTA - 1);
const ySaida = (k: number) => A / 2 + (k - 1) * 58;

// ---------------------------------------------------------------- camada fixa (calculada uma vez)
const MAX1 = Math.max(...W1.map(Math.abs));
const MAX2 = Math.max(...W2.map(Math.abs));
const CORTE1 = [...W1].map(Math.abs).sort((a, b) => b - a)[140];
const BASE1: { i: number; j: number; w: number; f: number }[] = [];
for (let i = 0; i < N_ENTRADAS; i++)
  for (let j = 0; j < N_OCULTA; j++) {
    const w = W1[i * N_OCULTA + j];
    if (Math.abs(w) >= CORTE1) BASE1.push({ i, j, w, f: Math.abs(w) / MAX1 });
  }
const BASE2: { j: number; k: number; w: number; f: number }[] = [];
for (let j = 0; j < N_OCULTA; j++)
  for (let k = 0; k < N_CLASSES; k++) {
    const w = W2[j * N_CLASSES + k];
    BASE2.push({ j, k, w, f: Math.abs(w) / MAX2 });
  }

/** Todas as ligações mais fortes e os neurônios, sem destaque: não muda entre os dias. */
const CamadaFixa = memo(function CamadaFixa() {
  return (
    <g>
      {BASE1.map(({ i, j, w, f }) => (
        <line
          key={`a${i}-${j}`}
          x1={X[0]}
          y1={yEntrada(i)}
          x2={X[1]}
          y2={yOculta(j)}
          stroke={w > 0 ? "var(--primary)" : "var(--muted-foreground)"}
          strokeWidth={0.4 + f * 0.9}
          opacity={0.06 + f * 0.18}
        />
      ))}
      {BASE2.map(({ j, k, w, f }) => (
        <line
          key={`b${j}-${k}`}
          x1={X[1]}
          y1={yOculta(j)}
          x2={X[2]}
          y2={ySaida(k)}
          stroke={w > 0 ? "var(--primary)" : "var(--muted-foreground)"}
          strokeWidth={0.4 + f * 0.6}
          opacity={0.05 + f * 0.15}
        />
      ))}
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
      {Array.from({ length: N_OCULTA }, (_, j) => (
        <circle
          key={`o${j}`}
          cx={X[1]}
          cy={yOculta(j)}
          r={2.6}
          fill="var(--card)"
          stroke="var(--muted-foreground)"
          strokeWidth={1}
        />
      ))}
      <text x={X[0]} y={A - 1} textAnchor="middle" fontSize={9} fill="var(--muted-foreground)">
        45 entradas
      </text>
      <text x={X[1]} y={A - 4} textAnchor="middle" fontSize={9} fill="var(--muted-foreground)">
        32 ocultos
      </text>
    </g>
  );
});

/**
 * Desenho da MLP 45 → 32 → 3 com os pesos reais do classificador v3.1.
 * Ao abrir um dia, o sinal percorre a rede uma vez (entradas → ocultos → saída) pelos
 * neurônios que mais pesam na classe que a placa escolheu (W2 positivos) e pelas entradas mais
 * fortes de cada um (|W1|). As entradas do dia não vêm da placa: nenhuma ativação é inventada.
 * Quem chama troca a `key` para rodar a animação de novo.
 */
export function RedeNeural({ classe }: { classe: number | null }) {
  const valida = classe === 0 || classe === 1 || classe === 2;
  const { ocultos, entradas } = useMemo(() => {
    if (!valida) return { ocultos: [] as number[], entradas: [] as { i: number; j: number }[] };
    const ocultos = Array.from({ length: N_OCULTA }, (_, j) => ({
      j,
      w: W2[j * N_CLASSES + classe],
    }))
      .filter((x) => x.w > 0)
      .sort((a, b) => b.w - a.w)
      .slice(0, 8)
      .map((x) => x.j);
    const entradas = ocultos.flatMap((j) =>
      Array.from({ length: N_ENTRADAS }, (_, i) => ({ i, j, a: Math.abs(W1[i * N_OCULTA + j]) }))
        .sort((a, b) => b.a - a.a)
        .slice(0, 4),
    );
    return { ocultos, entradas };
  }, [classe, valida]);

  const cor = valida ? COR_CLASSE[classe] : "var(--muted-foreground)";

  return (
    <svg
      viewBox={`0 0 ${L} ${A}`}
      className="rede-neural h-auto w-full"
      role="img"
      aria-label={`Rede neural 45 entradas, 32 neurônios ocultos e 3 classes; classe do dia: ${
        valida ? ROTULO[classe] : "sem classe"
      }`}
    >
      <CamadaFixa />

      {/* 1º: entradas → ocultos */}
      {entradas.map(({ i, j }, n) => (
        <line
          key={`fa${i}-${j}`}
          x1={X[0]}
          y1={yEntrada(i)}
          x2={X[1]}
          y2={yOculta(j)}
          pathLength={1}
          stroke={cor}
          strokeWidth={1}
          className="rede-traco"
          style={{ animationDelay: `${(n % 8) * 40}ms` }}
        />
      ))}
      {/* 2º: ocultos acendem */}
      {ocultos.map((j) => (
        <circle
          key={`fo${j}`}
          cx={X[1]}
          cy={yOculta(j)}
          r={3.8}
          fill={cor}
          className="rede-surge"
          style={{ animationDelay: "650ms" }}
        />
      ))}
      {/* 3º: ocultos → classe */}
      {ocultos.map((j, n) => (
        <line
          key={`fb${j}`}
          x1={X[1]}
          y1={yOculta(j)}
          x2={X[2]}
          y2={ySaida(classe ?? 0)}
          pathLength={1}
          stroke={cor}
          strokeWidth={1.8}
          className="rede-traco"
          style={{ animationDelay: `${800 + n * 40}ms` }}
        />
      ))}

      {[0, 1, 2].map((k) => {
        const on = valida && k === classe;
        return (
          <g key={`s${k}`}>
            {on && (
              <circle
                cx={X[2]}
                cy={ySaida(k)}
                r={16}
                fill={COR_CLASSE[k]}
                opacity={0.2}
                className="rede-surge"
                style={{ animationDelay: "1350ms" }}
              />
            )}
            <circle
              cx={X[2]}
              cy={ySaida(k)}
              r={9}
              fill="var(--card)"
              stroke={COR_CLASSE[k]}
              strokeWidth={1.6}
              opacity={valida && !on ? 0.45 : 1}
            />
            {on && (
              <circle
                cx={X[2]}
                cy={ySaida(k)}
                r={9}
                fill={COR_CLASSE[k]}
                className="rede-surge"
                style={{ animationDelay: "1300ms" }}
              />
            )}
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
    </svg>
  );
}
