import {
  AlertTriangle,
  CloudRain,
  Droplets,
  Layers,
  Leaf,
  Sun,
  Thermometer,
  TrendingUp,
  Wind,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import type { Resumo } from "@/api/tipos";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAgora } from "@/hooks/useAgora";
import {
  celsius,
  diaMes,
  diaMesDeData,
  ha,
  hora,
  litros,
  minutos,
  mm,
  numero,
  porcento,
  radiacao,
  vento,
} from "@/lib/formatar";
import { classeInfo, TEXTURA_SOLO } from "@/lib/rotulos";
import { cn } from "@/lib/utils";

export function Rotulo({
  icone: Icone,
  children,
}: {
  icone: LucideIcon;
  children: React.ReactNode;
}) {
  return (
    <p className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
      <Icone className="size-4" />
      {children}
    </p>
  );
}

export function NumeroGrande({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p className={cn("numeros font-display text-3xl font-semibold tracking-tight", className)}>
      {children}
    </p>
  );
}

// ---------------------------------------------------------------- linha 1

/** O essencial primeiro: a lâmina do dia é o primeiro número que o produtor vê. */
export function CardLamina({ resumo }: { resumo: Resumo }) {
  const d = resumo.ultimo_diario;
  const semPlaca = !resumo.dispositivo;
  return (
    <Card className="relative h-full overflow-hidden border-primary/40 bg-destaque shadow-sm">
      <Droplets
        aria-hidden
        className="pointer-events-none absolute -right-6 -bottom-8 size-44 text-primary/10"
      />
      <CardContent className="relative flex h-full flex-col gap-4">
        <Rotulo icone={Droplets}>Lâmina de hoje</Rotulo>
        {d ? (
          <>
            <div>
              <p className="numeros font-display text-5xl font-semibold tracking-tight text-primary sm:text-6xl">
                {numero(d.lamina_bruta)}
                <span className="ml-2 text-2xl font-medium sm:text-3xl">mm</span>
              </p>
              <p className="mt-2 text-base">
                {(d.lamina_bruta ?? 0) > 0 ? (
                  <>
                    ≈ <strong className="numeros">{litros(d.aplicar_l_planta)}</strong> por planta ·{" "}
                    <strong className="numeros">{minutos(d.minutos)}</strong> de válvula
                  </>
                ) : (
                  "Sem irrigação necessária hoje."
                )}
              </p>
              {d.aplicar_l_total != null && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {litros(d.aplicar_l_total)} no total do cultivo
                </p>
              )}
            </div>
            <p className="mt-auto text-sm text-muted-foreground">
              Fechamento de {diaMesDeData(d.data)} · calculado na placa às {hora(d.ts)} de{" "}
              {diaMes(d.ts)}
            </p>
          </>
        ) : semPlaca ? (
          <div className="flex flex-1 flex-col items-start justify-center gap-3">
            <p className="text-lg font-medium">Instale a placa neste cultivo</p>
            <p className="text-sm text-muted-foreground">
              A lâmina é calculada pela placa no fechamento de cada dia.
            </p>
            <Button asChild size="sm">
              <Link to="/dispositivo">Ir para Dispositivo</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-1 flex-col justify-center gap-1">
            <p className="text-lg font-medium">O primeiro fechamento sai às 00h00</p>
            <p className="text-sm text-muted-foreground">
              A placa calcula a lâmina à meia-noite, com os dados do dia completo.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function PillClasse({
  classe,
  grande = false,
}: {
  classe: number | null;
  grande?: boolean;
}) {
  const info = classeInfo(classe);
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-2 rounded-full border font-semibold",
        grande ? "px-4 py-2 text-lg" : "px-2.5 py-0.5 text-xs",
        info.fundo,
      )}
    >
      <span className={cn("rounded-full bg-current", grande ? "size-2.5" : "size-1.5")} />
      {info.rotulo}
    </span>
  );
}

export function CardEstado({ resumo }: { resumo: Resumo }) {
  const d = resumo.ultimo_diario;
  const semFonte = resumo.cultivo.fonte_irrigacao === "nenhuma";
  const avisos = d?.avisos ?? [];
  return (
    <Card className="h-full shadow-sm">
      <CardContent className="flex h-full flex-col gap-4">
        <Rotulo icone={Leaf}>Estado hídrico</Rotulo>
        {d ? (
          <>
            <PillClasse classe={d.classe} grande />
            <p className="text-sm text-muted-foreground">
              Classificador na placa · fechamento de {diaMesDeData(d.data)}
            </p>
            {d.classe == null && semFonte && (
              <p className="text-sm font-medium text-estado-moderado">
                Sem classe: registre a irrigação. Sem essa informação o classificador perde a
                maioria dos dias críticos.
              </p>
            )}
            {avisos.length > 0 && (
              <ul className="mt-auto grid gap-1.5">
                {avisos.slice(0, 3).map((aviso) => (
                  <li key={aviso} className="flex gap-2 text-sm text-estado-moderado">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                    <span>{aviso}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Aguardando o primeiro fechamento da placa.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- linha 2

export function CardFase({ resumo }: { resumo: Resumo }) {
  const { ciclo, ultimo_diario: d, cultivo } = resumo;
  const progresso = ciclo.ciclo_dias
    ? Math.min(100, Math.max(0, (ciclo.dias / ciclo.ciclo_dias) * 100))
    : 0;
  const referencia = cultivo.cultura_info?.referencia === "poda" ? "poda" : "floração";
  return (
    <Card className="h-full shadow-sm">
      <CardContent className="flex h-full flex-col gap-3">
        <Rotulo icone={TrendingUp}>Fase da cultura</Rotulo>
        <div>
          <p className="numeros font-display text-xl font-semibold">
            Dia {ciclo.dias} de {ciclo.ciclo_dias}
          </p>
          <p className="text-sm text-muted-foreground">
            {ciclo.fase_nome ?? cultivo.cultura_info?.nome ?? cultivo.cultura}
            {d?.kc != null && <> · Kc {numero(d.kc, 2)}</>}
          </p>
        </div>
        <Progress value={progresso} className="mt-auto h-2" aria-label="Progresso do ciclo" />
        {ciclo.fora_do_ciclo ? (
          <p className="text-xs font-medium text-estado-moderado">
            Fora do ciclo com dados: confira a data da {referencia}.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Contado a partir da {referencia}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function CardSolo({ resumo }: { resumo: Resumo }) {
  const c = resumo.cultivo;
  return (
    <Card className="h-full shadow-sm">
      <CardContent className="flex h-full flex-col gap-3">
        <Rotulo icone={Layers}>Solo</Rotulo>
        <div>
          <p className="font-display text-xl font-semibold">{TEXTURA_SOLO[c.textura_solo]}</p>
          <p className="numeros text-sm text-muted-foreground">
            TAW {numero(c.taw_mm, 0)} mm · raiz {numero(c.raiz_efetiva_m)} m
          </p>
        </div>
        <p className="numeros mt-auto text-sm">
          RAW <strong>{numero(c.raw_mm, 0)} mm</strong>
          <span className="text-muted-foreground"> · água facilmente disponível</span>
        </p>
      </CardContent>
    </Card>
  );
}

export function CardDemanda({ resumo }: { resumo: Resumo }) {
  const d = resumo.ultimo_diario;
  return (
    <Card className="h-full shadow-sm">
      <CardContent className="flex h-full flex-col gap-3">
        <Rotulo icone={Sun}>Demanda de ontem</Rotulo>
        {d ? (
          <>
            <div>
              <p className="numeros font-display text-xl font-semibold">ETc {mm(d.etc)}</p>
              <p className="numeros text-sm text-muted-foreground">
                ET₀ {mm(d.et0)} × Kc {numero(d.kc, 2)}
              </p>
            </div>
            <p className="mt-auto text-xs text-muted-foreground">
              Dia {diaMesDeData(d.data)} · chuva {mm(d.chuva)} · irrigação {mm(d.irrigacao)}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Sem fechamento ainda.</p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- linha 3

function ItemClima({
  icone: Icone,
  rotulo,
  valor,
  cor,
}: {
  icone: LucideIcon;
  rotulo: string;
  valor: string;
  cor?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className={cn("grid size-10 shrink-0 place-items-center rounded-lg bg-muted", cor)}>
        <Icone className="size-5" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{rotulo}</p>
        <p className="numeros font-semibold whitespace-nowrap">{valor}</p>
      </div>
    </div>
  );
}

export function CardClima({ resumo }: { resumo: Resumo }) {
  const agora = useAgora();
  const l = resumo.ultima_leitura;
  const hoje = resumo.ultimos_7_dias.at(-1);
  return (
    <Card className="h-full shadow-sm">
      <CardContent className="flex h-full flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Rotulo icone={Thermometer}>Clima agora</Rotulo>
          {l && (
            <span className="text-xs text-muted-foreground">
              Leitura das {hora(l.ts)} · {ha(l.ts, agora)}
            </span>
          )}
        </div>
        {l ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-4">
            <ItemClima
              icone={Thermometer}
              rotulo="Temperatura"
              valor={celsius(l.temp_c)}
              cor="text-estado-moderado"
            />
            <ItemClima
              icone={Droplets}
              rotulo="Umidade"
              valor={porcento(l.ur_pct)}
              cor="text-chuva"
            />
            <ItemClima icone={Wind} rotulo="Vento" valor={vento(l.vento_ms)} cor="text-etc" />
            <ItemClima
              icone={Sun}
              rotulo="Radiação"
              valor={radiacao(l.rad_wm2)}
              cor="text-estado-moderado"
            />
            <ItemClima
              icone={CloudRain}
              rotulo="Chuva hoje"
              valor={mm(hoje?.chuva ?? 0)}
              cor="text-chuva"
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Nenhuma leitura recebida ainda.</p>
        )}
      </CardContent>
    </Card>
  );
}
