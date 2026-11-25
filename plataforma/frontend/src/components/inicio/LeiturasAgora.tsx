import { CloudRain, Droplets, Radio, Sun, Thermometer, Wind, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { useLeituras } from "@/api/consultas";
import type { Resumo } from "@/api/tipos";
import { PillStatus } from "@/components/PillStatus";
import { Card, CardContent } from "@/components/ui/card";
import { useAgora } from "@/hooks/useAgora";
import { ha, hora, numero } from "@/lib/formatar";
import { cn } from "@/lib/utils";

const VARIAVEIS = ["temp_c", "ur_pct", "vento_ms", "rad_wm2", "chuva_mm"];
const JANELA_S = 24 * 3600;
const LACUNA_S = 2 * 3600; // sem leitura por mais que isso: a linha é interrompida

type Ponto = { ts: number; v: number };

/** Linha das últimas 24 h de uma variável, com cursor e valor ao passar o mouse. */
function Sparkline({
  pontos,
  de,
  ate,
  cor,
  casas,
  unidade,
}: {
  pontos: Ponto[];
  de: number;
  ate: number;
  cor: string;
  casas: number;
  unidade: string;
}) {
  const [foco, setFoco] = useState<Ponto | null>(null);
  if (pontos.length < 2) {
    return <div className="h-12 rounded-md bg-muted/50" aria-hidden />;
  }
  const valores = pontos.map((p) => p.v);
  let min = Math.min(...valores);
  let max = Math.max(...valores);
  if (max - min < 1e-6) {
    min -= 1;
    max += 1;
  }
  const x = (ts: number) => ((ts - de) / (ate - de)) * 100;
  const y = (v: number) => 30 - ((v - min) / (max - min)) * 26;

  // Segmentos contínuos (quebra nas lacunas, sem ligar pontos distantes).
  const segmentos: Ponto[][] = [];
  for (const p of pontos) {
    const atual = segmentos.at(-1);
    if (!atual || p.ts - atual.at(-1)!.ts > LACUNA_S) segmentos.push([p]);
    else atual.push(p);
  }
  const linha = segmentos
    .map((s) =>
      s.map((p, i) => `${i ? "L" : "M"}${x(p.ts).toFixed(2)},${y(p.v).toFixed(2)}`).join(""),
    )
    .join("");
  const area = segmentos
    .filter((s) => s.length > 1)
    .map(
      (s) =>
        `M${x(s[0].ts).toFixed(2)},32` +
        s.map((p) => `L${x(p.ts).toFixed(2)},${y(p.v).toFixed(2)}`).join("") +
        `L${x(s.at(-1)!.ts).toFixed(2)},32Z`,
    )
    .join("");

  function mover(e: React.PointerEvent<SVGSVGElement>) {
    const caixa = e.currentTarget.getBoundingClientRect();
    const ts = de + ((e.clientX - caixa.left) / caixa.width) * (ate - de);
    let melhor = pontos[0];
    for (const p of pontos) if (Math.abs(p.ts - ts) < Math.abs(melhor.ts - ts)) melhor = p;
    setFoco(melhor);
  }

  return (
    <div className="relative">
      <svg
        viewBox="0 0 100 32"
        preserveAspectRatio="none"
        className={cn("h-12 w-full touch-none overflow-visible", cor)}
        onPointerMove={mover}
        onPointerLeave={() => setFoco(null)}
        role="img"
        aria-label={`Últimas 24 horas: mínimo ${numero(min, casas)} ${unidade}, máximo ${numero(max, casas)} ${unidade}`}
      >
        <path d={area} className="fill-current opacity-10" />
        <path
          d={linha}
          className="fill-none stroke-current"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        {foco && (
          <line
            x1={x(foco.ts)}
            x2={x(foco.ts)}
            y1={0}
            y2={32}
            className="stroke-foreground/40"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      {foco && (
        <div
          className="pointer-events-none absolute -top-8 z-10 -translate-x-1/2 rounded-md border bg-popover px-2 py-0.5 text-xs whitespace-nowrap text-popover-foreground shadow-sm"
          style={{ left: `${Math.min(88, Math.max(12, x(foco.ts)))}%` }}
        >
          <span className="text-muted-foreground">{hora(foco.ts)}</span>{" "}
          <strong className="numeros">
            {numero(foco.v, casas)} {unidade}
          </strong>
        </div>
      )}
    </div>
  );
}

function Sensor({
  icone: Icone,
  rotulo,
  valor,
  casas,
  unidade,
  cor,
  fundo,
  marca,
  pontos,
  de,
  ate,
  rodape,
}: {
  icone: LucideIcon;
  rotulo: string;
  valor: number | null | undefined;
  casas: number;
  unidade: string;
  cor: string;
  fundo: string;
  marca: number;
  pontos?: Ponto[];
  de: number;
  ate: number;
  rodape?: React.ReactNode;
}) {
  const min = pontos?.length ? Math.min(...pontos.map((p) => p.v)) : null;
  const max = pontos?.length ? Math.max(...pontos.map((p) => p.v)) : null;
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2">
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg", fundo, cor)}>
          <Icone className="size-4" />
        </span>
        <p className="truncate text-sm font-medium text-muted-foreground">{rotulo}</p>
      </div>
      <p
        key={marca}
        className="leitura-nova numeros w-fit rounded-md font-display text-4xl font-semibold tracking-tight sm:text-5xl"
      >
        {valor == null ? "—" : numero(valor, casas)}
        <span className="ml-1.5 text-lg font-medium text-muted-foreground sm:text-xl">
          {unidade}
        </span>
      </p>
      {pontos ? (
        <>
          <Sparkline pontos={pontos} de={de} ate={ate} cor={cor} casas={casas} unidade={unidade} />
          <p className="numeros text-xs text-muted-foreground">
            {min == null ? (
              "Sem leituras nas últimas 24 h"
            ) : (
              <>
                24 h: mín {numero(min, casas)} · máx {numero(max, casas)}
              </>
            )}
          </p>
        </>
      ) : (
        rodape
      )}
    </div>
  );
}

/** Primeira coisa da tela: o que os sensores estão lendo agora, grande e com as últimas 24 h. */
export function LeiturasAgora({ resumo }: { resumo: Resumo }) {
  const agora = useAgora();
  const l = resumo.ultima_leitura;
  const hoje = resumo.ultimos_7_dias.at(-1);
  // A janela anda junto com a última leitura: chegou leitura nova, a série é buscada de novo.
  const ate = (l?.ts ?? Math.floor(agora.getTime() / 1000 / 600) * 600) + 60;
  const de = ate - JANELA_S;
  const serie = useLeituras(
    resumo.cultivo.id,
    new Date(de * 1000).toISOString(),
    new Date(ate * 1000).toISOString(),
    l ? VARIAVEIS : [],
  );
  const pontos = useMemo(() => {
    const porVar: Record<string, Ponto[]> = {};
    for (const v of VARIAVEIS) porVar[v] = [];
    for (const p of serie.data?.pontos ?? []) {
      for (const v of VARIAVEIS) {
        const valor = p[v];
        if (typeof valor === "number") porVar[v].push({ ts: p.ts, v: valor });
      }
    }
    return porVar;
  }, [serie.data]);
  const chuva24h = pontos.chuva_mm.reduce((soma, p) => soma + p.v, 0);
  const marca = l?.ts ?? 0;

  return (
    <Card className="shadow-sm">
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Radio className="size-5 text-primary" /> Estação agora
            </h2>
            <p className="text-sm text-muted-foreground">
              {l ? (
                <>
                  Leitura das <strong className="numeros text-foreground">{hora(l.ts)}</strong> ·{" "}
                  {ha(l.ts, agora)}
                  {l.rssi != null && <> · sinal Wi-Fi {l.rssi} dBm</>}
                </>
              ) : (
                "Nenhuma leitura recebida ainda."
              )}
            </p>
          </div>
          <PillStatus dispositivo={resumo.dispositivo} />
        </div>

        {l && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <Sensor
              icone={Thermometer}
              rotulo="Temperatura"
              valor={l.temp_c}
              casas={1}
              unidade="°C"
              cor="text-estado-moderado"
              fundo="bg-estado-moderado/12"
              marca={marca}
              pontos={pontos.temp_c}
              de={de}
              ate={ate}
            />
            <Sensor
              icone={Droplets}
              rotulo="Umidade"
              valor={l.ur_pct}
              casas={0}
              unidade="%"
              cor="text-chuva"
              fundo="bg-chuva/12"
              marca={marca}
              pontos={pontos.ur_pct}
              de={de}
              ate={ate}
            />
            <Sensor
              icone={Sun}
              rotulo="Radiação"
              valor={l.rad_wm2}
              casas={0}
              unidade="W/m²"
              cor="text-estado-moderado"
              fundo="bg-estado-moderado/12"
              marca={marca}
              pontos={pontos.rad_wm2}
              de={de}
              ate={ate}
            />
            <Sensor
              icone={Wind}
              rotulo="Vento"
              valor={l.vento_ms}
              casas={1}
              unidade="m/s"
              cor="text-etc"
              fundo="bg-etc/12"
              marca={marca}
              pontos={pontos.vento_ms}
              de={de}
              ate={ate}
            />
            <Sensor
              icone={CloudRain}
              rotulo="Chuva hoje"
              valor={hoje?.chuva ?? 0}
              casas={1}
              unidade="mm"
              cor="text-chuva"
              fundo="bg-chuva/12"
              marca={marca}
              de={de}
              ate={ate}
              rodape={
                <div className="mt-auto grid gap-1 text-xs text-muted-foreground">
                  <p className="numeros">
                    Últimas 24 h: <strong className="text-foreground">{numero(chuva24h)} mm</strong>
                  </p>
                  <p className="numeros">Na última leitura: {numero(l.chuva_mm ?? 0)} mm</p>
                </div>
              }
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
