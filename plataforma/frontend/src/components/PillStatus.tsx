import type { DispositivoResumo } from "@/api/tipos";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAgora } from "@/hooks/useAgora";
import { diaHora, ha, hora, noFuso } from "@/lib/formatar";
import { cn } from "@/lib/utils";

const ESTILO = {
  ao_vivo: "bg-estado-adequado/12 text-estado-adequado border-estado-adequado/30",
  atrasado: "bg-estado-moderado/12 text-estado-moderado border-estado-moderado/30",
  sem_contato: "bg-sem-contato/12 text-sem-contato border-sem-contato/30",
  sincronizando: "bg-sincronizando/12 text-sincronizando border-sincronizando/30",
} as const;

function mesmoDia(a: Date, b: Date) {
  return noFuso(a).toDateString() === noFuso(b).toDateString();
}

/** Pill do topo (regra 9.6): de quando é o dado, sempre. */
export function PillStatus({
  dispositivo,
}: {
  dispositivo:
    | Pick<
        DispositivoResumo,
        "serial" | "status" | "ultima_telemetria" | "ultimo_contato" | "sincronizando"
      >
    | null
    | undefined;
}) {
  const agora = useAgora();
  if (!dispositivo) {
    return (
      <span className="inline-flex h-8 items-center rounded-full border bg-muted px-3 text-xs font-medium text-muted-foreground">
        Sem placa instalada
      </span>
    );
  }

  const { status, ultima_telemetria, ultimo_contato, sincronizando } = dispositivo;
  let texto: string;
  if (status === "ao_vivo") texto = `Ao vivo · ${hora(ultima_telemetria)}`;
  else if (status === "atrasado") texto = `Atualizado ${ha(ultima_telemetria, agora)}`;
  else if (status === "sincronizando")
    texto = `Sincronizando ${sincronizando} leitura${sincronizando === 1 ? "" : "s"}`;
  else if (!ultimo_contato) texto = "Sem contato";
  else
    texto = mesmoDia(new Date(ultimo_contato), agora)
      ? `Sem contato desde ${hora(ultimo_contato)}`
      : `Sem contato desde ${diaHora(ultimo_contato)}`;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex h-8 items-center gap-2 rounded-full border px-3 text-xs font-medium whitespace-nowrap",
            ESTILO[status],
          )}
        >
          <span className="relative flex size-2">
            {status === "ao_vivo" && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" />
            )}
            <span className="relative inline-flex size-2 rounded-full bg-current" />
          </span>
          {texto}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        Placa {dispositivo.serial}
        {ultimo_contato && <> · último contato {diaHora(ultimo_contato)}</>}
      </TooltipContent>
    </Tooltip>
  );
}
