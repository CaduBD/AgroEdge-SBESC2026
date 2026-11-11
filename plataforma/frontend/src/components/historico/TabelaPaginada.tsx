import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export interface MetaColuna {
  /** Alinha à direita (números) */
  numero?: boolean;
}

/** Tabela com paginação no cliente (TanStack Table), no estilo do painel. */
export function TabelaPaginada<T>({
  dados,
  colunas,
  porPagina = 15,
  vazio = "Nada neste período.",
}: {
  dados: T[];
  colunas: ColumnDef<T, unknown>[];
  porPagina?: number;
  vazio?: string;
}) {
  const tabela = useReactTable({
    data: dados,
    columns: colunas,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: porPagina } },
  });
  const { pageIndex } = tabela.getState().pagination;
  const total = dados.length;
  const inicio = total ? pageIndex * porPagina + 1 : 0;
  const fim = Math.min(total, (pageIndex + 1) * porPagina);

  return (
    <div className="grid gap-3">
      <div className="overflow-x-auto rounded-lg border">
        <Table className="numeros">
          <TableHeader className="bg-muted/50">
            {tabela.getHeaderGroups().map((grupo) => (
              <TableRow key={grupo.id}>
                {grupo.headers.map((h) => (
                  <TableHead
                    key={h.id}
                    className={cn(
                      "whitespace-nowrap",
                      (h.column.columnDef.meta as MetaColuna | undefined)?.numero && "text-right",
                    )}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {tabela.getRowModel().rows.length ? (
              tabela.getRowModel().rows.map((linha) => (
                <TableRow key={linha.id}>
                  {linha.getVisibleCells().map((celula) => (
                    <TableCell
                      key={celula.id}
                      className={cn(
                        "whitespace-nowrap",
                        (celula.column.columnDef.meta as MetaColuna | undefined)?.numero &&
                          "text-right",
                      )}
                    >
                      {flexRender(celula.column.columnDef.cell, celula.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={colunas.length}
                  className="h-20 text-center text-muted-foreground"
                >
                  {vazio}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      {total > porPagina && (
        <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="numeros">
            {inicio}–{fim} de {total.toLocaleString("pt-BR")}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => tabela.previousPage()}
              disabled={!tabela.getCanPreviousPage()}
              aria-label="Página anterior"
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="numeros px-2">
              {pageIndex + 1} / {tabela.getPageCount()}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => tabela.nextPage()}
              disabled={!tabela.getCanNextPage()}
              aria-label="Próxima página"
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
