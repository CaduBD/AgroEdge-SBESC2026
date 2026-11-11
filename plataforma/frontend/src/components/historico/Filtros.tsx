import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import { CalendarRange, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import type { DateRange } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { diaMesDeData } from "@/lib/formatar";
import { hojeLocal, type Periodo, type TipoPeriodo } from "@/lib/periodo";
import { cn } from "@/lib/utils";

import { VARIAVEIS } from "./variaveis";

const CHIPS: { tipo: Exclude<TipoPeriodo, "personalizado">; rotulo: string }[] = [
  { tipo: "7d", rotulo: "7 dias" },
  { tipo: "30d", rotulo: "30 dias" },
  { tipo: "ciclo", rotulo: "Ciclo atual" },
];

function Chip({
  ativo,
  onClick,
  children,
}: {
  ativo: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={ativo}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm font-medium transition-colors",
        ativo
          ? "border-primary bg-primary text-primary-foreground"
          : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** Chips de período + intervalo personalizado (calendário). */
export function FiltroPeriodo({
  periodo,
  aoMudar,
}: {
  periodo: Periodo;
  aoMudar: (tipo: TipoPeriodo, de?: string, ate?: string) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [intervalo, setIntervalo] = useState<DateRange | undefined>(() => ({
    from: parseISO(periodo.de),
    to: parseISO(periodo.ate),
  }));
  const hoje = parseISO(hojeLocal());

  const aplicar = () => {
    if (!intervalo?.from) return;
    const de = format(intervalo.from, "yyyy-MM-dd");
    const ate = format(intervalo.to ?? intervalo.from, "yyyy-MM-dd");
    aoMudar("personalizado", de, ate);
    setAberto(false);
  };

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Período">
      {CHIPS.map((c) => (
        <Chip key={c.tipo} ativo={periodo.tipo === c.tipo} onClick={() => aoMudar(c.tipo)}>
          {c.rotulo}
        </Chip>
      ))}
      <Popover
        open={aberto}
        onOpenChange={(a) => {
          setAberto(a);
          if (a) setIntervalo({ from: parseISO(periodo.de), to: parseISO(periodo.ate) });
        }}
      >
        <PopoverTrigger asChild>
          <span>
            <Chip ativo={periodo.tipo === "personalizado"}>
              <CalendarRange className="size-3.5" />
              {periodo.tipo === "personalizado"
                ? `${diaMesDeData(periodo.de)} – ${diaMesDeData(periodo.ate)}`
                : "Personalizado"}
            </Chip>
          </span>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="range"
            locale={ptBR}
            numberOfMonths={1}
            selected={intervalo}
            onSelect={setIntervalo}
            defaultMonth={intervalo?.from}
            disabled={{ after: hoje }}
          />
          <div className="flex items-center justify-between gap-2 border-t p-3">
            <span className="text-sm text-muted-foreground">
              {intervalo?.from
                ? `${format(intervalo.from, "dd/MM")} – ${intervalo.to ? format(intervalo.to, "dd/MM") : "…"}`
                : "Escolha o início e o fim"}
            </span>
            <Button size="sm" onClick={aplicar} disabled={!intervalo?.from}>
              Aplicar
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

/** Seletor das variáveis do clima. */
export function SeletorVariaveis({
  selecionadas,
  aoMudar,
}: {
  selecionadas: string[];
  aoMudar: (v: string[]) => void;
}) {
  const alternar = (chave: string, marcado: boolean) => {
    const proximo = marcado
      ? VARIAVEIS.map((v) => v.chave).filter((k) => k === chave || selecionadas.includes(k))
      : selecionadas.filter((k) => k !== chave);
    if (proximo.length) aoMudar(proximo);
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8">
          <SlidersHorizontal className="size-3.5" />
          Variáveis ({selecionadas.length})
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Mostrar no gráfico</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {VARIAVEIS.map((v) => (
          <DropdownMenuCheckboxItem
            key={v.chave}
            checked={selecionadas.includes(v.chave)}
            onCheckedChange={(m) => alternar(v.chave, !!m)}
            onSelect={(e) => e.preventDefault()}
          >
            <span className="size-2.5 rounded-sm" style={{ background: v.cor }} />
            {v.rotulo}
            {v.diagnostico && <span className="ml-auto text-xs text-muted-foreground">placa</span>}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
