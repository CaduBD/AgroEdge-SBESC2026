import type { ColumnDef } from "@tanstack/react-table";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  XAxis,
  YAxis,
} from "recharts";

import type { Lacuna, Serie } from "@/api/tipos";
import { Card, CardContent } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { diaHora } from "@/lib/formatar";

import { marcasDiarias, quebrarNasLacunas, rotuloDia, rotuloDiaHora } from "./eixo";
import { type MetaColuna, TabelaPaginada } from "./TabelaPaginada";
import { formatarVariavel, variavel } from "./variaveis";

const ROTULO_RESOLUCAO = {
  bruta: "cada leitura (15 min)",
  hora: "média por hora (chuva somada)",
  dia: "média por dia (chuva somada)",
} as const;

type Ponto = { ts: number } & Record<string, number | null>;

function Dica({
  active,
  payload,
  chave,
}: {
  active?: boolean;
  payload?: { payload: Ponto }[];
  chave: string;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <p className="text-muted-foreground">{rotuloDiaHora(p.ts)}</p>
      <p className="numeros font-semibold">{formatarVariavel(chave, p[chave])}</p>
    </div>
  );
}

/** Sombreia as lacunas de contato (regra 9.7), com o rótulo "sem contato". */
function areasSemContato(lacunas: Lacuna[], rotulo: boolean) {
  return lacunas.map((l) => (
    <ReferenceArea
      key={l.inicio}
      x1={l.inicio}
      x2={l.fim}
      fill="var(--sem-contato)"
      fillOpacity={0.14}
      strokeOpacity={0}
      ifOverflow="hidden"
      label={
        rotulo
          ? {
              value: "sem contato",
              position: "insideTop",
              fontSize: 10,
              fill: "var(--muted-foreground)",
            }
          : undefined
      }
    />
  ));
}

function GraficoVariavel({
  serie,
  chave,
  dominio,
  primeiro,
}: {
  serie: Serie;
  chave: string;
  dominio: [number, number];
  primeiro: boolean;
}) {
  const v = variavel(chave);
  const config = { [chave]: { label: v.rotulo, color: v.cor } } satisfies ChartConfig;
  const marcas = marcasDiarias(dominio[0], dominio[1]);
  const comuns = {
    margin: { top: 14, right: 8, left: 0, bottom: 0 },
  };
  const eixoX = (
    <XAxis
      dataKey="ts"
      type="number"
      scale="time"
      domain={dominio}
      ticks={marcas}
      tickFormatter={rotuloDia}
      tickLine={false}
      axisLine={false}
      tick={{ fontSize: 11 }}
      allowDataOverflow
    />
  );
  const eixoY = (
    <YAxis
      tickLine={false}
      axisLine={false}
      width={42}
      tick={{ fontSize: 11 }}
      tickFormatter={(n: number) => n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}
    />
  );
  const dica = <ChartTooltip content={<Dica chave={chave} />} />;

  return (
    <div className="grid gap-1">
      <p className="flex items-center gap-2 text-sm font-medium">
        <span className="size-2.5 rounded-sm" style={{ background: v.cor }} />
        {v.rotulo} <span className="font-normal text-muted-foreground">({v.unidade})</span>
      </p>
      <ChartContainer config={config} className="aspect-auto h-44 w-full">
        {v.tipo === "barra" ? (
          <BarChart data={serie.pontos} {...comuns}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            {areasSemContato(serie.lacunas, primeiro)}
            {eixoX}
            {eixoY}
            {dica}
            <Bar dataKey={chave} fill={`var(--color-${chave})`} radius={[2, 2, 0, 0]} />
          </BarChart>
        ) : (
          <LineChart data={quebrarNasLacunas(serie.pontos, serie.lacunas, [chave])} {...comuns}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            {areasSemContato(serie.lacunas, primeiro)}
            {eixoX}
            {eixoY}
            {dica}
            <Line
              dataKey={chave}
              type="monotone"
              stroke={`var(--color-${chave})`}
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        )}
      </ChartContainer>
    </div>
  );
}

export function AbaClima({ serie, dominio }: { serie: Serie; dominio: [number, number] }) {
  const colunas: ColumnDef<Ponto, unknown>[] = [
    {
      id: "ts",
      header: serie.resolucao === "dia" ? "Dia" : "Data e hora",
      cell: ({ row }) => diaHora(row.original.ts),
    },
    ...serie.variaveis.map((chave): ColumnDef<Ponto, unknown> => ({
      id: chave,
      header: variavel(chave).rotulo,
      meta: { numero: true } satisfies MetaColuna,
      cell: ({ row }) => formatarVariavel(chave, row.original[chave]),
    })),
  ];
  const linhas = [...serie.pontos].reverse(); // mais recente primeiro

  return (
    <div className="grid gap-4">
      <Card className="shadow-sm">
        <CardContent className="grid gap-5">
          <p className="text-xs text-muted-foreground">
            {ROTULO_RESOLUCAO[serie.resolucao]}
            {serie.lacunas.length > 0 && (
              <>
                {" · "}
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block size-2.5 rounded-sm bg-sem-contato/30" />
                  {serie.lacunas.length} período{serie.lacunas.length > 1 ? "s" : ""} sem contato
                </span>
              </>
            )}
          </p>
          {serie.variaveis.map((chave, i) => (
            <GraficoVariavel
              key={chave}
              serie={serie}
              chave={chave}
              dominio={dominio}
              primeiro={i === 0}
            />
          ))}
        </CardContent>
      </Card>
      <TabelaPaginada dados={linhas} colunas={colunas} porPagina={20} />
    </div>
  );
}
