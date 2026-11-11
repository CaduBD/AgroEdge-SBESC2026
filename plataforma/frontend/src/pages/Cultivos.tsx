import {
  Archive,
  ArchiveRestore,
  Cpu,
  LayoutDashboard,
  MoreHorizontal,
  Pencil,
  Plus,
  Sprout,
  Trash2,
  Warehouse,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { mensagemDeErro } from "@/api/cliente";
import {
  useArquivarCultivo,
  useCulturas,
  useCultivosDaFazenda,
  useExcluirFazenda,
  useFazendas,
} from "@/api/consultas";
import type { Cultivo, Fazenda } from "@/api/tipos";
import { DialogoFazenda } from "@/components/cultivos/DialogoFazenda";
import { EstadoConfiguracao } from "@/components/cultivos/EstadoConfiguracao";
import { EstadoVazio } from "@/components/EstadoVazio";
import { PillClasse } from "@/components/inicio/Cards";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";

function CartaoCultivo({ cultivo }: { cultivo: Cultivo }) {
  const { data: culturas } = useCulturas();
  const cultura = culturas?.find((c) => c.chave === cultivo.cultura);
  const arquivar = useArquivarCultivo();
  const navegar = useNavigate();
  const [confirmar, setConfirmar] = useState(false);
  const ciclo = cultura?.ciclo_dias ?? 0;
  const progresso = ciclo ? Math.min(100, Math.max(0, (cultivo.dia_do_ciclo / ciclo) * 100)) : 0;

  return (
    <Card className="gap-0 py-0 shadow-sm">
      <CardContent className="grid gap-3 p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold">{cultivo.nome}</p>
            <p className="truncate text-sm text-muted-foreground">
              {cultura?.nome ?? cultivo.cultura}
            </p>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="-mt-1 -mr-2 size-8" aria-label="Ações">
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => navegar(`/cultivos/${cultivo.id}/inicio`)}>
                <LayoutDashboard className="size-4" /> Abrir no Início
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => navegar(`/cultivos/${cultivo.id}/editar`)}>
                <Pencil className="size-4" /> Editar
              </DropdownMenuItem>
              {!cultivo.arquivado && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => setConfirmar(true)}>
                    <Archive className="size-4" /> Arquivar
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="grid gap-1.5">
          <div className="flex items-center justify-between text-sm">
            <span className="numeros">
              Dia {cultivo.dia_do_ciclo} de {ciclo}
            </span>
            {cultivo.ultima_classe != null && <PillClasse classe={cultivo.ultima_classe} />}
          </div>
          <Progress value={progresso} className="h-1.5" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          {cultivo.configuracao ? (
            <span className="inline-flex items-center gap-1.5 text-sm font-medium">
              <Cpu className="size-3.5 text-muted-foreground" />
              {cultivo.configuracao.serial}
            </span>
          ) : null}
          <EstadoConfiguracao configuracao={cultivo.configuracao} />
          {cultivo.arquivado && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <ArchiveRestore className="size-3" /> Arquivado
            </span>
          )}
        </div>
      </CardContent>

      <AlertDialog open={confirmar} onOpenChange={setConfirmar}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Arquivar “{cultivo.nome}”?</AlertDialogTitle>
            <AlertDialogDescription>
              O cultivo sai das listas e do seletor do topo, mas o histórico continua guardado.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Voltar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                arquivar.mutate(cultivo.id, {
                  onSuccess: () => toast.success("Cultivo arquivado."),
                  onError: (e) => toast.error(mensagemDeErro(e)),
                })
              }
            >
              Arquivar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

function SecaoFazenda({
  fazenda,
  arquivados,
  aoEditar,
}: {
  fazenda: Fazenda;
  arquivados: boolean;
  aoEditar: (f: Fazenda) => void;
}) {
  const cultivos = useCultivosDaFazenda(fazenda.id, arquivados);
  const excluir = useExcluirFazenda();
  const [confirmar, setConfirmar] = useState(false);

  return (
    <section className="grid gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-primary">
            <Warehouse className="size-4" />
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{fazenda.nome}</h2>
            {fazenda.municipio && (
              <p className="text-sm text-muted-foreground">{fazenda.municipio}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/cultivos/novo?fazenda=${fazenda.id}`}>
              <Plus className="size-4" /> Cultivo
            </Link>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="size-8" aria-label="Ações da fazenda">
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => aoEditar(fazenda)}>
                <Pencil className="size-4" /> Editar fazenda
              </DropdownMenuItem>
              <DropdownMenuItem
                variant="destructive"
                disabled={fazenda.n_cultivos > 0}
                onSelect={() => setConfirmar(true)}
              >
                <Trash2 className="size-4" />
                {fazenda.n_cultivos > 0 ? "Excluir (só sem cultivos)" : "Excluir fazenda"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {cultivos.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : cultivos.data?.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cultivos.data.map((c) => (
            <CartaoCultivo key={c.id} cultivo={c} />
          ))}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
          Nenhum cultivo nesta fazenda.{" "}
          <Link
            className="font-medium text-primary underline-offset-4 hover:underline"
            to={`/cultivos/novo?fazenda=${fazenda.id}`}
          >
            Cadastrar o primeiro
          </Link>
        </p>
      )}

      <AlertDialog open={confirmar} onOpenChange={setConfirmar}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir “{fazenda.nome}”?</AlertDialogTitle>
            <AlertDialogDescription>
              A fazenda não tem cultivos. Isso não pode ser desfeito.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Voltar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                excluir.mutate(fazenda.id, {
                  onSuccess: () => toast.success("Fazenda excluída."),
                  onError: (e) => toast.error(mensagemDeErro(e)),
                })
              }
            >
              Excluir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}

/** Tela Cultivos (seção 12.5): cultivos agrupados por fazenda. */
export function Cultivos() {
  const fazendas = useFazendas();
  const [arquivados, setArquivados] = useState(false);
  const [dialogo, setDialogo] = useState<{ aberto: boolean; fazenda: Fazenda | null }>({
    aberto: false,
    fazenda: null,
  });

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Cultivos</h1>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch id="arquivados" checked={arquivados} onCheckedChange={setArquivados} />
            <Label htmlFor="arquivados" className="text-sm font-normal text-muted-foreground">
              Mostrar arquivados
            </Label>
          </div>
          <Button variant="outline" onClick={() => setDialogo({ aberto: true, fazenda: null })}>
            <Warehouse className="size-4" /> Nova fazenda
          </Button>
          {fazendas.data?.length ? (
            <Button asChild>
              <Link to="/cultivos/novo">
                <Plus className="size-4" /> Novo cultivo
              </Link>
            </Button>
          ) : null}
        </div>
      </div>

      {fazendas.isPending ? (
        <Skeleton className="h-56 rounded-xl" />
      ) : !fazendas.data?.length ? (
        <EstadoVazio
          icone={Sprout}
          titulo="Crie sua primeira fazenda"
          texto="Comece pela fazenda; depois cadastre os cultivos e instale a placa em um deles."
          acao={
            <Button onClick={() => setDialogo({ aberto: true, fazenda: null })}>
              <Warehouse className="size-4" /> Nova fazenda
            </Button>
          }
        />
      ) : (
        fazendas.data.map((f) => (
          <SecaoFazenda
            key={f.id}
            fazenda={f}
            arquivados={arquivados}
            aoEditar={(fazenda) => setDialogo({ aberto: true, fazenda })}
          />
        ))
      )}

      <DialogoFazenda
        aberto={dialogo.aberto}
        fazenda={dialogo.fazenda}
        aoMudar={(aberto) => setDialogo((d) => ({ ...d, aberto }))}
      />
    </div>
  );
}
