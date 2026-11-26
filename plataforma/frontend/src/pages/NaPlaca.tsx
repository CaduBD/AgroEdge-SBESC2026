import {
  AlertCircle,
  AlertTriangle,
  BrainCircuit,
  ChevronRight,
  CircuitBoard,
  CloudRain,
  Droplets,
  Expand,
  FlaskConical,
  RefreshCw,
  Sigma,
  Sprout,
  Thermometer,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { ErroApi, mensagemDeErro } from "@/api/cliente";
import { useDiarios, useIrrigacoes, useResumo } from "@/api/consultas";
import type { Diario, Irrigacao } from "@/api/tipos";
import { EstadoVazio } from "@/components/EstadoVazio";
import { PillClasse } from "@/components/inicio/Cards";
import { RedeNeural } from "@/components/placa/RedeNeural";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { diaMesDeData, diaSemana, hora, mm, numero } from "@/lib/formatar";
import { resolverPeriodo } from "@/lib/periodo";
import { classeInfo } from "@/lib/rotulos";
import { cn } from "@/lib/utils";
import { NaoEncontrada } from "@/pages/NaoEncontrada";

const COR_CLASSE = ["var(--estado-adequado)", "var(--estado-moderado)", "var(--estado-critico)"];

const fmt = (v: number | null | undefined, casas = 1, un = "") =>
  v == null ? "—" : `${numero(v, casas)}${un}`;

const nomeFase = (f: string | null) =>
  f ? f.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "—";

/** Dia seguinte em AAAA-MM-DD. */
function diaSeguinte(data: string) {
  const d = new Date(`${data}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** A irrigação que a placa abriu na manhã seguinte ao fechamento (00:00 a 12:00, horário local). */
function irrigacaoDaManha(d: Diario, lista: Irrigacao[]) {
  const ini = Date.parse(`${diaSeguinte(d.data)}T00:00:00-03:00`) / 1000;
  return lista.find((i) => i.ts_inicio >= ini && i.ts_inicio < ini + 12 * 3600) ?? null;
}

function Passo({
  n,
  icone: Icone,
  titulo,
  sub,
  children,
  className,
}: {
  n: number;
  icone: typeof Sigma;
  titulo: string;
  sub: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "relative flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs",
        className,
      )}
    >
      <header className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
          {n}
        </span>
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 leading-tight font-semibold">
            <Icone className="size-4 text-primary" />
            {titulo}
          </h3>
          <p className="text-xs text-muted-foreground">{sub}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

function Grande({ valor, un, rotulo }: { valor: string; un: string; rotulo: string }) {
  return (
    <div>
      <p className="numeros text-4xl leading-none font-semibold tracking-tight">
        {valor}
        <span className="ml-1 text-base font-medium text-muted-foreground">{un}</span>
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{rotulo}</p>
    </div>
  );
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed py-1 text-sm last:border-0">
      <span className="text-muted-foreground">{rotulo}</span>
      <span className="numeros font-medium">{valor}</span>
    </div>
  );
}

function BarraSolo({
  deficit,
  taw,
  raw,
  classe,
}: {
  deficit: number;
  taw: number;
  raw: number;
  classe: number | null;
}) {
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / taw) * 100))}%`;
  const cor =
    classe != null && classe >= 0 && classe <= 2 ? COR_CLASSE[classe] : "var(--muted-foreground)";
  return (
    <div className="grid gap-1.5">
      <div className="relative h-5 overflow-hidden rounded-full bg-muted">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: pct(deficit), background: cor }}
        />
        <div className="absolute inset-y-0 w-0.5 bg-foreground/70" style={{ left: pct(raw) }} />
      </div>
      <div className="relative h-4 text-[11px] text-muted-foreground">
        <span className="absolute left-0">0</span>
        <span className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: pct(raw) }}>
          RAW {fmt(raw, 0)}
        </span>
        <span className="absolute right-0">TAW {fmt(taw, 0)} mm</span>
      </div>
    </div>
  );
}

/** Tela "Na placa": reprodução visual do fechamento diário que roda dentro da BitDogLab. */
export function NaPlaca() {
  const { cultivoId: idTexto } = useParams();
  const cultivoId = Number(idTexto);
  const resumo = useResumo(cultivoId);
  const periodo = resolverPeriodo("30d", null, null, resumo.data?.cultivo.data_referencia);
  const diarios = useDiarios(cultivoId, periodo.de, periodo.ate);
  const irrigacoes = useIrrigacoes(cultivoId, periodo.de, periodo.ate);

  const dias = useMemo(
    () =>
      [...(diarios.data ?? [])]
        .filter((d) => d.et0 != null)
        .sort((a, b) => b.data.localeCompare(a.data) || b.ts - a.ts),
    [diarios.data],
  );
  const [sel, setSel] = useState<number | null>(null);

  const indice = Math.max(
    0,
    dias.findIndex((d) => d.ts === sel),
  );
  const d = dias[indice] as Diario | undefined;

  if (resumo.isPending || diarios.isPending) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-16 rounded-xl" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );
  }
  const erro = resumo.error ?? diarios.error;
  if (erro) {
    if (erro instanceof ErroApi && erro.status === 404) return <NaoEncontrada />;
    return (
      <EstadoVazio
        icone={AlertCircle}
        titulo="Não foi possível carregar"
        texto={mensagemDeErro(erro)}
        acao={
          <Button variant="outline" onClick={() => diarios.refetch()}>
            <RefreshCw className="size-4" /> Tentar de novo
          </Button>
        }
      />
    );
  }

  const cultivo = resumo.data!.cultivo;
  const irr = d ? irrigacaoDaManha(d, irrigacoes.data ?? []) : null;
  const entrou = (d?.chuva ?? 0) + (d?.irrigacao ?? 0);

  return (
    <div className="grid gap-5">
      {/* ------------------------------------------------ cabeçalho */}
      <div className="relative overflow-hidden rounded-2xl bg-[#10372a] px-6 py-7 text-white sm:px-8">
        <p className="flex items-center gap-2 font-mono text-xs tracking-[0.22em] text-[#95d5b2] uppercase">
          <CircuitBoard className="size-4" /> Dentro da BitDogLab · RP2040 · MicroPython
        </p>
        <h1 className="mt-3 max-w-4xl text-3xl leading-tight font-semibold tracking-tight sm:text-5xl">
          O processo que roda <span className="text-[#95d5b2]">na placa</span>, à meia-noite
        </h1>
        <p className="mt-3 max-w-3xl text-sm text-white/75 sm:text-base">
          Esta tela só <strong className="text-white">mostra</strong> o fechamento diário que a
          placa já calculou e enviou: sensores → Penman-Monteith → cultura → balanço do solo → rede
          neural → irrigação. Nenhum desses números é calculado no servidor.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-white/10 px-3 py-1 text-xs">{cultivo.nome}</span>
          {d && (
            <span
              className={cn(
                "rounded-full px-3 py-1 text-xs font-semibold",
                d.simulado ? "bg-amber-300/20 text-amber-200" : "bg-[#95d5b2]/20 text-[#b7f0cf]",
              )}
            >
              {d.simulado
                ? "Dia simulado com o código do firmware"
                : `Enviado pela placa ${d.serial ?? ""}`}
            </span>
          )}
          <div className="ml-auto flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => document.documentElement.requestFullscreen?.().catch(() => {})}
              className="bg-white/10 text-white hover:bg-white/20"
            >
              <Expand className="size-4" /> Tela cheia
            </Button>
          </div>
        </div>
      </div>

      {dias.length === 0 || !d ? (
        <EstadoVazio
          icone={CircuitBoard}
          titulo="Nenhum fechamento nos últimos 30 dias"
          texto="Quando a placa fechar o primeiro dia (à meia-noite), o cálculo aparece aqui."
        />
      ) : (
        <>
          {/* ------------------------------------------------ faixa de dias */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {dias.map((x) => {
              const ativo = x.ts === d.ts;
              return (
                <button
                  key={x.ts}
                  type="button"
                  onClick={() => setSel(x.ts)}
                  className={cn(
                    "flex min-w-16 shrink-0 flex-col items-center gap-1 rounded-lg border px-2.5 py-2 text-xs",
                    ativo
                      ? "border-primary bg-primary text-primary-foreground"
                      : "bg-card hover:bg-accent",
                  )}
                >
                  <span className="font-semibold">{diaMesDeData(x.data)}</span>
                  <span
                    className={cn("capitalize", ativo ? "opacity-85" : "text-muted-foreground")}
                  >
                    {diaSemana(x.data)}
                  </span>
                  <span className="flex h-3 items-center gap-1">
                    <span
                      className="size-2 rounded-full"
                      style={{
                        background:
                          x.classe != null ? COR_CLASSE[x.classe] : "var(--muted-foreground)",
                      }}
                    />
                    {x.simulado === false && (
                      <CircuitBoard className="size-3" aria-label="enviado pela placa" />
                    )}
                  </span>
                </button>
              );
            })}
          </div>

          {/* ------------------------------------------------ os 5 passos */}
          <div className="grid gap-3 min-[1800px]:grid-cols-[1fr_1fr_1fr_1.15fr] lg:grid-cols-2">
            <Passo
              n={1}
              icone={Thermometer}
              titulo="Sensores do dia"
              sub="~144 leituras de 10 min, guardadas na flash"
            >
              <div>
                <Linha
                  rotulo="Temperatura máx / mín"
                  valor={`${fmt(d.tmax)} / ${fmt(d.tmin)} °C`}
                />
                <Linha rotulo="Umidade média (AM2302)" valor={fmt(d.ur, 0, "%")} />
                <Linha rotulo="Radiação (SN-300AL)" valor={fmt(d.rs, 1, " MJ/m²")} />
                <Linha rotulo="Vento a 2 m (Met One)" valor={fmt(d.u2, 1, " m/s")} />
                <Linha rotulo="Chuva (pluviômetro)" valor={mm(d.chuva)} />
              </div>
            </Passo>

            <Passo
              n={2}
              icone={Sigma}
              titulo="Penman-Monteith"
              sub="FAO-56, equação 6, em ponto flutuante na RP2040"
            >
              <Grande
                valor={fmt(d.et0, 2)}
                un="mm"
                rotulo="ETo: quanto a grama de referência perderia de água"
              />
              <p className="rounded-lg bg-muted px-3 py-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                ETo = [0,408·Δ·(Rn−G) + γ·900/(T+273)·u₂·(es−ea)] / [Δ + γ·(1+0,34·u₂)]
              </p>
            </Passo>

            <Passo
              n={3}
              icone={Sprout}
              titulo="Cultura"
              sub={`${cultivo.cultura_info?.nome ?? d.cultura ?? ""} · dia ${d.dap ?? "—"} do ciclo`}
            >
              <Linha
                rotulo="Fase"
                valor={
                  cultivo.cultura_info?.fases?.find((f) => f.chave === d.fase)?.nome ??
                  nomeFase(d.fase)
                }
              />
              <Linha rotulo="Coeficiente Kc" valor={fmt(d.kc, 2)} />
              <Grande
                valor={fmt(d.etc, 2)}
                un="mm"
                rotulo={`ETc = Kc × ETo = ${fmt(d.kc, 2)} × ${fmt(d.et0, 2)}`}
              />
            </Passo>

            <Passo
              n={4}
              icone={Droplets}
              titulo="Balanço do solo"
              sub="o que entrou menos o que a planta consumiu"
            >
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-muted px-3 py-2">
                  <p className="flex items-center gap-1 text-xs text-muted-foreground">
                    <CloudRain className="size-3.5" /> Entrou
                  </p>
                  <p className="numeros font-semibold">{mm(entrou)}</p>
                  <p className="text-[11px] text-muted-foreground">
                    chuva {fmt(d.chuva)} + irrigação {fmt(d.irrigacao)}
                  </p>
                </div>
                <div className="rounded-lg bg-muted px-3 py-2">
                  <p className="text-xs text-muted-foreground">Saiu (ETc)</p>
                  <p className="numeros font-semibold">{mm(d.etc)}</p>
                </div>
              </div>
              <Grande
                valor={fmt(d.deficit)}
                un="mm"
                rotulo="déficit de água no solo depois do dia"
              />
              {d.deficit != null && (d.taw ?? cultivo.taw_mm) > 0 && (
                <BarraSolo
                  deficit={d.deficit}
                  taw={d.taw ?? cultivo.taw_mm}
                  raw={cultivo.raw_mm}
                  classe={d.classe}
                />
              )}
            </Passo>
          </div>

          <Passo
            n={5}
            icone={BrainCircuit}
            titulo="Classificador na placa (rede neural MLP, 6,6 KB)"
            sub="45 entradas (28 dias de clima e manejo) → 32 neurônios → 3 classes"
          >
            <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
              <div className="rounded-xl bg-muted/50 p-3">
                <RedeNeural key={d.ts} classe={d.classe} />
                <p className="mt-1 text-center text-[11px] text-muted-foreground">
                  Ligações com os pesos reais do modelo v3.1; em destaque, os neurônios que mais
                  pesam na classe do dia. A classe é a que a placa enviou.
                </p>
              </div>
              <div className="grid gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Resultado da placa</p>
                  <div className="mt-1">
                    <PillClasse classe={d.classe} grande />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl border p-3">
                    <p className="text-xs text-muted-foreground">Lâmina recomendada</p>
                    <p className="numeros text-2xl font-semibold">{mm(d.lamina_bruta)}</p>
                  </div>
                  <div className="rounded-xl border p-3">
                    <p className="text-xs text-muted-foreground">Válvula</p>
                    <p className="numeros text-2xl font-semibold">{fmt(d.minutos, 0, " min")}</p>
                  </div>
                </div>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-4 py-3 text-sm",
                    irr ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                  )}
                >
                  <ChevronRight className="size-5 shrink-0" />
                  {irr ? (
                    <span>
                      <strong>A placa abriu a válvula</strong> às {hora(irr.ts_inicio)} de{" "}
                      {diaMesDeData(diaSeguinte(d.data))}: {fmt(irr.minutos, 0)} min, {mm(irr.mm)} (
                      {irr.origem === "automatica" ? "automática" : "manual"})
                      {irr.minutos != null && d.minutos != null && irr.minutos < d.minutos - 1 && (
                        <span className="block text-xs opacity-80">
                          Turno limitado a 8 h; o restante entra no balanço dos próximos dias.
                        </span>
                      )}
                    </span>
                  ) : (
                    <span>
                      {d.minutos
                        ? "Nenhuma irrigação registrada na manhã seguinte."
                        : `${classeInfo(d.classe).rotulo}: sem irrigação necessária.`}
                    </span>
                  )}
                </div>
                {d.avisos.length > 0 && (
                  <ul className="grid gap-1 text-xs text-muted-foreground">
                    {d.avisos.map((a) => (
                      <li key={a} className="flex gap-1.5">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-estado-moderado" />
                        {a}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </Passo>

          {d.simulado && (
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <FlaskConical className="mt-0.5 size-3.5 shrink-0" />
              Dia de demonstração: clima horário real do Open-Meteo para Petrolina, fechado pelo
              mesmo código do firmware (main.processar_dia, classificador v3.1) rodando fora da
              placa.
            </p>
          )}
        </>
      )}
    </div>
  );
}
