import { BarChart3 } from "lucide-react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceArea, XAxis, YAxis } from "recharts";

import type { DiaResumo } from "@/api/tipos";
import { Card, CardContent } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
} from "@/components/ui/chart";
import { diaMesDeData, diaSemana, mm } from "@/lib/formatar";

import { PillClasse, Rotulo } from "./Cards";

const config = {
  chuva: { label: "Chuva", color: "var(--chuva)" },
  irrigacao: { label: "Irrigação aplicada", color: "var(--irrigacao)" },
  etc: { label: "ETc", color: "var(--etc)" },
} satisfies ChartConfig;

interface Ponto extends DiaResumo {
  rotulo: string;
}

function Dica({ active, payload }: { active?: boolean; payload?: { payload: Ponto }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="grid min-w-44 gap-1.5 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">
        {p.hoje ? "Hoje" : diaSemana(p.data)} · {diaMesDeData(p.data)}
      </p>
      {(["chuva", "irrigacao", "etc"] as const).map((k) => (
        <div key={k} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-sm" style={{ background: config[k].color }} />
            {config[k].label}
          </span>
          <span className="numeros font-medium">{mm(p[k])}</span>
        </div>
      ))}
      <div className="mt-0.5">
        {p.fechado ? (
          <PillClasse classe={p.classe} />
        ) : (
          <span className="text-muted-foreground">Dia ainda sem fechamento</span>
        )}
      </div>
    </div>
  );
}

/** Últimos 7 dias: barras de chuva e irrigação aplicada, linha de ETc; hoje destacado. */
export function GraficoSemana({ dias }: { dias: DiaResumo[] }) {
  const pontos: Ponto[] = dias.map((d) => ({
    ...d,
    rotulo: d.hoje ? "Hoje" : `${diaSemana(d.data)} ${diaMesDeData(d.data)}`,
  }));
  const hoje = pontos.find((p) => p.hoje);
  const vazio = pontos.every((p) => p.chuva == null && p.irrigacao == null && p.etc == null);

  return (
    <Card className="shadow-sm">
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Rotulo icone={BarChart3}>Últimos 7 dias</Rotulo>
          <span className="text-xs text-muted-foreground">mm por dia</span>
        </div>
        {vazio ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ainda não há dados desta semana.
          </p>
        ) : (
          <ChartContainer config={config} className="aspect-auto h-64 w-full sm:h-72">
            <ComposedChart data={pontos} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              {hoje && (
                <ReferenceArea
                  x1={hoje.rotulo}
                  x2={hoje.rotulo}
                  fill="var(--primary)"
                  fillOpacity={0.07}
                  ifOverflow="extendDomain"
                />
              )}
              <XAxis
                dataKey="rotulo"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                interval={0}
                tick={{ fontSize: 11 }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={44}
                tickFormatter={(v: number) => `${v.toLocaleString("pt-BR")}`}
                tick={{ fontSize: 11 }}
              />
              <ChartTooltip cursor={{ fill: "var(--muted)", opacity: 0.5 }} content={<Dica />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar
                dataKey="chuva"
                fill="var(--color-chuva)"
                radius={[4, 4, 0, 0]}
                maxBarSize={28}
              />
              <Bar
                dataKey="irrigacao"
                fill="var(--color-irrigacao)"
                radius={[4, 4, 0, 0]}
                maxBarSize={28}
              />
              <Line
                dataKey="etc"
                type="monotone"
                stroke="var(--color-etc)"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "var(--color-etc)" }}
                connectNulls
              />
            </ComposedChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
