import type { ColumnDef } from "@tanstack/react-table";
import { AlertTriangle } from "lucide-react";
import { Bar, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import type { Diario } from "@/api/tipos";
import { PillClasse } from "@/components/inicio/Cards";
import { Card, CardContent } from "@/components/ui/card";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
} from "@/components/ui/chart";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { dataCompleta, diaMesDeData, minutos, mm } from "@/lib/formatar";

import { type MetaColuna, TabelaPaginada } from "./TabelaPaginada";

const config = {
  chuva: { label: "Chuva", color: "var(--chuva)" },
  irrigacao: { label: "Irrigação aplicada", color: "var(--irrigacao)" },
  etc: { label: "ETc", color: "var(--etc)" },
  lamina_bruta: { label: "Lâmina indicada", color: "var(--estado-moderado)" },
} satisfies ChartConfig;

function Dica({ active, payload }: { active?: boolean; payload?: { payload: Diario }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="grid min-w-48 gap-1.5 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">{dataCompleta(`${d.data}T12:00:00Z`)}</p>
      {(Object.keys(config) as (keyof typeof config)[]).map((k) => (
        <div key={k} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-sm" style={{ background: config[k].color }} />
            {config[k].label}
          </span>
          <span className="numeros font-medium">{mm(d[k])}</span>
        </div>
      ))}
      <PillClasse classe={d.classe} />
    </div>
  );
}

const num = { numero: true } satisfies MetaColuna;

const colunas: ColumnDef<Diario, unknown>[] = [
  { id: "data", header: "Data", cell: ({ row }) => diaMesDeData(row.original.data) },
  { id: "et0", header: "ET₀", meta: num, cell: ({ row }) => mm(row.original.et0) },
  { id: "etc", header: "ETc", meta: num, cell: ({ row }) => mm(row.original.etc) },
  { id: "chuva", header: "Chuva", meta: num, cell: ({ row }) => mm(row.original.chuva) },
  {
    id: "irrigacao",
    header: "Irrigação",
    meta: num,
    cell: ({ row }) => mm(row.original.irrigacao),
  },
  {
    id: "classe",
    header: "Classe",
    cell: ({ row }) => {
      const d = row.original;
      return (
        <span className="inline-flex items-center gap-1.5">
          <PillClasse classe={d.classe} />
          {d.avisos.length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertTriangle className="size-3.5 text-estado-moderado" aria-label="Avisos" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                {d.avisos.map((a) => (
                  <p key={a}>{a}</p>
                ))}
              </TooltipContent>
            </Tooltip>
          )}
        </span>
      );
    },
  },
  { id: "lamina", header: "Lâmina", meta: num, cell: ({ row }) => mm(row.original.lamina_bruta) },
  { id: "minutos", header: "Minutos", meta: num, cell: ({ row }) => minutos(row.original.minutos) },
];

export function AbaFechamentos({ diarios }: { diarios: Diario[] }) {
  const pontos = diarios.map((d) => ({ ...d, rotulo: diaMesDeData(d.data) }));
  return (
    <div className="grid gap-4">
      <Card className="shadow-sm">
        <CardContent>
          <ChartContainer config={config} className="aspect-auto h-72 w-full">
            <ComposedChart data={pontos} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey="rotulo"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11 }}
                minTickGap={16}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={40}
                tick={{ fontSize: 11 }}
                tickFormatter={(n: number) => n.toLocaleString("pt-BR")}
              />
              <ChartTooltip cursor={{ fill: "var(--muted)", opacity: 0.5 }} content={<Dica />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar
                dataKey="chuva"
                fill="var(--color-chuva)"
                radius={[3, 3, 0, 0]}
                maxBarSize={18}
              />
              <Bar
                dataKey="irrigacao"
                fill="var(--color-irrigacao)"
                radius={[3, 3, 0, 0]}
                maxBarSize={18}
              />
              <Line
                dataKey="etc"
                type="monotone"
                stroke="var(--color-etc)"
                strokeWidth={2}
                dot={false}
                connectNulls
              />
              <Line
                dataKey="lamina_bruta"
                type="stepAfter"
                stroke="var(--color-lamina_bruta)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
                connectNulls
              />
            </ComposedChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <TabelaPaginada dados={[...diarios].reverse()} colunas={colunas} />
    </div>
  );
}
