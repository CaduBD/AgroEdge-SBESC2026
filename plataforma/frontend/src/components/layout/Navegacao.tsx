import { Cpu, History, LayoutDashboard, LogOut, Sprout, UserRound } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useEu, useLogout } from "@/api/consultas";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { lerCultivoSalvo } from "@/hooks/useCultivoSelecionado";
import { cn } from "@/lib/utils";

function itens(cultivoId: number | null) {
  const base = cultivoId ? `/cultivos/${cultivoId}` : "";
  return [
    { rotulo: "Início", icone: LayoutDashboard, para: cultivoId ? `${base}/inicio` : "/" },
    { rotulo: "Histórico", icone: History, para: cultivoId ? `${base}/historico` : "/historico" },
    { rotulo: "Cultivos", icone: Sprout, para: "/cultivos" },
    { rotulo: "Dispositivo", icone: Cpu, para: "/dispositivo" },
    { rotulo: "Conta", icone: UserRound, para: "/conta" },
  ];
}

/** Itens da barra lateral; usado na barra fixa (desktop) e no menu Sheet (celular). */
export function Navegacao({
  compacta = false,
  aoNavegar,
  cultivoId,
}: {
  compacta?: boolean;
  aoNavegar?: () => void;
  cultivoId: number | null;
}) {
  const id = cultivoId ?? lerCultivoSalvo();
  return (
    <nav className="flex flex-col gap-1">
      {itens(id).map((item) => {
        const link = (
          <NavLink
            key={item.rotulo}
            to={item.para}
            end
            onClick={aoNavegar}
            className={({ isActive }) =>
              cn(
                "flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                compacta && "justify-center px-0",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )
            }
          >
            <item.icone className="size-[18px] shrink-0" />
            {!compacta && <span>{item.rotulo}</span>}
          </NavLink>
        );
        return compacta ? (
          <Tooltip key={item.rotulo}>
            <TooltipTrigger asChild>{link}</TooltipTrigger>
            <TooltipContent side="right">{item.rotulo}</TooltipContent>
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

export function RodapeUsuario({ compacta = false }: { compacta?: boolean }) {
  const { data: usuario } = useEu();
  const logout = useLogout();
  const navegar = useNavigate();
  const iniciais = (usuario?.nome ?? "?")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const sair = () =>
    logout.mutate(undefined, {
      onSuccess: () => navegar("/login", { replace: true }),
      onError: () => toast.error("Não foi possível sair. Tente de novo."),
    });

  return (
    <div className={cn("flex items-center gap-3", compacta && "flex-col")}>
      <Avatar className="size-9">
        <AvatarFallback className="bg-accent text-xs font-semibold text-accent-foreground">
          {iniciais}
        </AvatarFallback>
      </Avatar>
      {!compacta && (
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{usuario?.nome}</p>
          <p className="truncate text-xs text-muted-foreground">{usuario?.email}</p>
        </div>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" onClick={sair} aria-label="Sair">
            <LogOut className="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent side={compacta ? "right" : "top"}>Sair</TooltipContent>
      </Tooltip>
    </div>
  );
}
