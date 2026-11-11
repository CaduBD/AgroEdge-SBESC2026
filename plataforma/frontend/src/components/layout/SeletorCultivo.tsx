import { Check, ChevronsUpDown, Cpu } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import type { Selecao } from "@/hooks/useCultivoSelecionado";
import { salvarCultivo } from "@/hooks/useCultivoSelecionado";
import { cn } from "@/lib/utils";

/** Combobox "Fazenda › Cultivo" do topo, com o serial da placa instalada embaixo. */
export function SeletorCultivo({ selecao }: { selecao: Selecao }) {
  const [aberto, setAberto] = useState(false);
  const navegar = useNavigate();
  const { pathname } = useLocation();
  const { cultivo, fazenda, grupos, carregando } = selecao;

  if (carregando) return <Skeleton className="h-11 w-56 rounded-lg" />;
  if (grupos.every((g) => g.cultivos.length === 0)) {
    return <span className="text-sm text-muted-foreground">Nenhum cultivo cadastrado</span>;
  }

  const escolher = (id: number) => {
    setAberto(false);
    salvarCultivo(id);
    const pagina = pathname.endsWith("/historico") ? "historico" : "inicio";
    navegar(`/cultivos/${id}/${pagina}`);
  };

  return (
    <Popover open={aberto} onOpenChange={setAberto}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          role="combobox"
          aria-expanded={aberto}
          className="h-auto w-full max-w-full min-w-0 justify-start gap-2 overflow-hidden px-2 py-1.5 text-left sm:w-auto"
        >
          <span className="min-w-0 flex-1">
            <span className="flex min-w-0 items-center gap-1.5 text-sm font-semibold">
              {fazenda ? (
                <>
                  <span className="hidden truncate font-medium text-muted-foreground sm:inline">
                    {fazenda.nome}
                  </span>
                  <span className="hidden text-muted-foreground sm:inline">›</span>
                  <span className="truncate">{cultivo?.nome}</span>
                </>
              ) : (
                "Escolha um cultivo"
              )}
            </span>
            <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
              <Cpu className="size-3" />
              {cultivo?.configuracao?.serial ?? "sem placa instalada"}
            </span>
          </span>
          <ChevronsUpDown className="ml-1 size-4 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <Command>
          <CommandInput placeholder="Buscar cultivo ou fazenda…" />
          <CommandList>
            <CommandEmpty>Nenhum cultivo encontrado.</CommandEmpty>
            {grupos
              .filter((g) => g.cultivos.length > 0)
              .map(({ fazenda: f, cultivos }) => (
                <CommandGroup key={f.id} heading={f.nome}>
                  {cultivos.map((c) => (
                    <CommandItem
                      key={c.id}
                      value={`${f.nome} ${c.nome} ${c.id}`}
                      onSelect={() => escolher(c.id)}
                    >
                      <Check
                        className={cn("size-4", c.id === cultivo?.id ? "opacity-100" : "opacity-0")}
                      />
                      <div className="min-w-0">
                        <p className="truncate">{c.nome}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {c.configuracao?.serial ?? "sem placa"}
                        </p>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
