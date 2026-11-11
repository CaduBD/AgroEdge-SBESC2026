import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export function EstadoVazio({
  icone: Icone,
  titulo,
  texto,
  acao,
  className,
}: {
  icone: LucideIcon;
  titulo: string;
  texto?: React.ReactNode;
  acao?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-card px-6 py-12 text-center",
        className,
      )}
    >
      <div className="grid size-12 place-items-center rounded-full bg-accent text-primary">
        <Icone className="size-6" />
      </div>
      <h2 className="text-lg font-semibold">{titulo}</h2>
      {texto && <p className="max-w-md text-sm text-muted-foreground">{texto}</p>}
      {acao && <div className="mt-2">{acao}</div>}
    </div>
  );
}
