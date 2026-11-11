import { CheckCircle2, Cpu, Loader2 } from "lucide-react";

import type { ConfiguracaoPlaca } from "@/api/tipos";
import { cn } from "@/lib/utils";

/** "Aguardando a placa…" até ela confirmar a versão; depois "Aplicado na placa (vN)". */
export function EstadoConfiguracao({
  configuracao,
  className,
}: {
  configuracao: ConfiguracaoPlaca | null | undefined;
  className?: string;
}) {
  if (!configuracao) {
    return (
      <span
        className={cn("inline-flex items-center gap-1.5 text-sm text-muted-foreground", className)}
      >
        <Cpu className="size-3.5" /> Sem placa instalada
      </span>
    );
  }
  return configuracao.aplicada ? (
    <span
      className={cn("inline-flex items-center gap-1.5 text-sm text-estado-adequado", className)}
    >
      <CheckCircle2 className="size-3.5" /> Aplicado na placa (v{configuracao.cfg_v})
    </span>
  ) : (
    <span
      className={cn("inline-flex items-center gap-1.5 text-sm text-estado-moderado", className)}
      title={`Versão ${configuracao.cfg_v} enviada; a placa confirmou a ${configuracao.cfg_v_aplicada ?? "nenhuma"}`}
    >
      <Loader2 className="size-3.5 animate-spin" /> Aguardando a placa… (v{configuracao.cfg_v})
    </span>
  );
}
