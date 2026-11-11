import { Menu, PanelLeftClose, PanelLeftOpen, WifiOff } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router-dom";

import { useConectado } from "@/api/conexao";
import { useResumo } from "@/api/consultas";
import { Logo } from "@/components/Logo";
import { PillStatus } from "@/components/PillStatus";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useCultivoSelecionado } from "@/hooks/useCultivoSelecionado";
import { useStream } from "@/hooks/useStream";
import { cn } from "@/lib/utils";

import { Navegacao, RodapeUsuario } from "./Navegacao";
import { SeletorCultivo } from "./SeletorCultivo";

const CHAVE_RECOLHIDA = "agroedge.barra-recolhida";

function lerRecolhida() {
  try {
    return localStorage.getItem(CHAVE_RECOLHIDA) === "1";
  } catch {
    return false;
  }
}

/** Layout geral (seção 12.4): barra lateral recolhível; abaixo de 768 px vira menu (Sheet). */
export function Layout() {
  const selecao = useCultivoSelecionado();
  const resumo = useResumo(selecao.cultivo ? (selecao.cultivoId ?? undefined) : undefined);
  const conectado = useConectado();
  useStream(true);
  const [recolhida, setRecolhida] = useState(lerRecolhida);
  const [menuAberto, setMenuAberto] = useState(false);

  const alternar = () => {
    setRecolhida((r) => {
      try {
        localStorage.setItem(CHAVE_RECOLHIDA, r ? "0" : "1");
      } catch {
        /* ignora */
      }
      return !r;
    });
  };

  return (
    <div className="flex min-h-svh">
      {/* Barra lateral (desktop) */}
      <aside
        className={cn(
          "sticky top-0 hidden h-svh shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 md:flex",
          recolhida ? "w-[72px]" : "w-60",
        )}
      >
        <div className={cn("flex h-16 items-center px-4", recolhida && "justify-center px-0")}>
          <Logo compacto={recolhida} />
        </div>
        <div className="flex-1 px-3 py-2">
          <Navegacao compacta={recolhida} cultivoId={selecao.cultivoId} />
        </div>
        <div className="px-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={alternar}
            className={cn(
              "w-full justify-start text-muted-foreground",
              recolhida && "justify-center",
            )}
            aria-label={recolhida ? "Expandir barra lateral" : "Recolher barra lateral"}
          >
            {recolhida ? (
              <PanelLeftOpen className="size-4" />
            ) : (
              <PanelLeftClose className="size-4" />
            )}
            {!recolhida && "Recolher"}
          </Button>
        </div>
        <Separator className="my-2" />
        <div className="px-3 pb-4">
          <RodapeUsuario compacta={recolhida} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior */}
        <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
          <div className="flex h-16 items-center gap-2 px-3 sm:px-6">
            <Sheet open={menuAberto} onOpenChange={setMenuAberto}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden" aria-label="Abrir menu">
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent
                side="left"
                className="flex w-72 flex-col gap-0 bg-sidebar p-0"
                onOpenAutoFocus={(e) => e.preventDefault()}
              >
                <SheetHeader className="h-16 justify-center px-4">
                  <SheetTitle asChild>
                    <div>
                      <Logo />
                    </div>
                  </SheetTitle>
                </SheetHeader>
                <div className="flex-1 px-3 py-2">
                  <Navegacao cultivoId={selecao.cultivoId} aoNavegar={() => setMenuAberto(false)} />
                </div>
                <Separator />
                <div className="p-4">
                  <RodapeUsuario />
                </div>
              </SheetContent>
            </Sheet>

            <div className="min-w-0 flex-1">
              <SeletorCultivo selecao={selecao} />
            </div>
            {selecao.cultivo && <PillStatus dispositivo={resumo.data?.dispositivo} />}
          </div>
          {!conectado && (
            <div className="flex items-center justify-center gap-2 border-t bg-estado-moderado/12 px-4 py-1.5 text-xs font-medium text-estado-moderado">
              <WifiOff className="size-3.5" />
              Sem conexão com o servidor. Tentando de novo…
            </div>
          )}
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-3 py-5 sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
