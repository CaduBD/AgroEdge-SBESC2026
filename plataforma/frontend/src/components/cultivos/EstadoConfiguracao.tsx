import { CheckCircle2, Cpu, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import type { ConfiguracaoPlaca } from "@/api/tipos";
import { avisarUmaVez, idToastConfig } from "@/lib/toasts";
import { cn } from "@/lib/utils";

/**
 * Toast "Configuração aplicada" quando o estado muda de aguardando para aplicado na tela.
 * Cobre o caso em que o evento do SSE se perdeu (aba em segundo plano, reconexão): a tela se
 * atualiza ao voltar, e o toast sai mesmo assim.
 */
function useAvisoAplicada(configuracao: ConfiguracaoPlaca | null | undefined) {
  const anterior = useRef<{ chave: string; aplicada: boolean } | null>(null);
  useEffect(() => {
    if (!configuracao) {
      anterior.current = null;
      return;
    }
    const chave = idToastConfig(configuracao.instalacao_id, configuracao.cfg_v);
    const antes = anterior.current;
    if (antes && antes.chave === chave && !antes.aplicada && configuracao.aplicada) {
      avisarUmaVez(chave, () =>
        toast.success(`Configuração v${configuracao.cfg_v} aplicada na placa`, { id: chave }),
      );
    }
    anterior.current = { chave, aplicada: configuracao.aplicada };
  }, [configuracao]);
}

/** "Aguardando a placa…" até ela confirmar a versão; depois "Aplicado na placa (vN)". */
export function EstadoConfiguracao({
  configuracao,
  className,
}: {
  configuracao: ConfiguracaoPlaca | null | undefined;
  className?: string;
}) {
  useAvisoAplicada(configuracao);
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
