import type { ColumnDef } from "@tanstack/react-table";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import type { Irrigacao } from "@/api/tipos";
import { Card, CardContent } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { diaHora, diaMes, mm, minutos, noFuso, numero } from "@/lib/formatar";
import type { Periodo } from "@/lib/periodo";
import { ESTADO_IRRIGACAO, ORIGEM_IRRIGACAO } from "@/lib/rotulos";
import { cn } from "@/lib/utils";
import { addDays, format, parseISO } from "date-fns";

import { type MetaColuna, TabelaPaginada } from "./TabelaPaginada";

const config = {
  automatica: { label: "Automática", color: "var(--irrigacao)" },
  manual: { label: "Manual", color: "var(--etc)" },
} satisfies ChartConfig;

const ESTILO_ESTADO: Record<Irrigacao["estado"], string> = {
  iniciada: "text-sincronizando",
  concluida: "text-estado-adequado",
  cancelada: "text-muted-foreground",
  interrompida: "text-estado-moderado",
};

const num = { numero: true } satisfies MetaColuna;

const colunas: ColumnDef<Irrigacao, unknown>[] = [
  { id: "inicio", header: "Início", cell: ({ row }) => diaHora(row.original.ts_inicio) },
  {
    id: "fim",
    header: "Fim",
    cell: ({ row }) => (row.original.ts_fim ? diaHora(row.original.ts_fim) : "—"),
  },
  { id: "minutos", header: "Duração", meta: num, cell: ({ row }) => minutos(row.original.minutos) },
  { id: "mm", header: "Lâmina", meta: num, cell: ({ row }) => mm(row.original.mm) },
  { id: "origem", header: "Origem", cell: ({ row }) => ORIGEM_IRRIGACAO[row.original.origem] },
  {
    id: "estado",
    header: "Estado",
    cell: ({ row }) => (
      <span className={cn("font-medium", ESTILO_ESTADO[row.original.estado])}>
        {ESTADO_IRRIGACAO[row.original.estado]}
      </span>
    ),
  },
];

interface Dia {
  data: string;
  rotulo: string;
  automatica: number;
  manual: number;
}

/** Soma por dia (local) e origem, com todos os dias do período no eixo. */
function porDia(irrigacoes: Irrigacao[], periodo: Periodo): Dia[] {
  const dias = new Map<string, Dia>();
  for (let d = parseISO(periodo.de); d <= parseISO(periodo.ate); d = addDays(d, 1)) {
    const chave = format(d, "yyyy-MM-dd");
    dias.set(chave, { data: chave, rotulo: format(d, "dd/MM"), automatica: 0, manual: 0 });
  }
  for (const i of irrigacoes) {
    const dia = dias.get(format(noFuso(i.ts_inicio), "yyyy-MM-dd"));
    if (dia && i.mm) dia[i.origem] += i.mm;
  }
  return [...dias.values()];
}

function Dica({ active, payload }: { active?: boolean; payload?: { payload: Dia }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="grid gap-1 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="font-semibold">{d.rotulo}</p>
      <p className="numeros">Automática: {mm(d.automatica)}</p>
      <p className="numeros">Manual: {mm(d.manual)}</p>
    </div>
  );
}

export function AbaIrrigacoes({
  irrigacoes,
  periodo,
}: {
  irrigacoes: Irrigacao[];
  periodo: Periodo;
}) {
  const totalMm = irrigacoes.reduce((s, i) => s + (i.mm ?? 0), 0);
  const totalMin = irrigacoes.reduce((s, i) => s + (i.minutos ?? 0), 0);
  return (
    <div className="grid gap-4">
      <Card className="shadow-sm">
        <CardContent className="grid gap-3">
          <p className="numeros text-sm text-muted-foreground">
            {irrigacoes.length} irrigaç{irrigacoes.length === 1 ? "ão" : "ões"} · {mm(totalMm)} ·{" "}
            {numero(totalMin / 60)} h de válvula
            {irrigacoes.length > 0 && <> · última em {diaMes(irrigacoes.at(-1)!.ts_inicio)}</>}
          </p>
          <ChartContainer config={config} className="aspect-auto h-56 w-full">
            <BarChart
              data={porDia(irrigacoes, periodo)}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
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
              <Bar
                dataKey="automatica"
                stackId="a"
                fill="var(--color-automatica)"
                maxBarSize={22}
              />
              <Bar
                dataKey="manual"
                stackId="a"
                fill="var(--color-manual)"
                radius={[3, 3, 0, 0]}
                maxBarSize={22}
              />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
      <TabelaPaginada
        dados={[...irrigacoes].reverse()}
        colunas={colunas}
        vazio="Nenhuma irrigação neste período."
      />
    </div>
  );
}
