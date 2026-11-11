import { AlertCircle, RefreshCw } from "lucide-react";
import { useParams } from "react-router-dom";

import { ErroApi, mensagemDeErro } from "@/api/cliente";
import { useResumo } from "@/api/consultas";
import {
  CardDemanda,
  CardClima,
  CardEstado,
  CardFase,
  CardLamina,
  CardSolo,
} from "@/components/inicio/Cards";
import { CardValvula } from "@/components/inicio/CardValvula";
import { GraficoSemana } from "@/components/inicio/GraficoSemana";
import { EstadoVazio } from "@/components/EstadoVazio";
import { NaoEncontrada } from "@/pages/NaoEncontrada";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

function Carregando() {
  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <Skeleton className="h-56 rounded-xl lg:col-span-7" />
      <Skeleton className="h-56 rounded-xl lg:col-span-5" />
      <Skeleton className="h-36 rounded-xl lg:col-span-4" />
      <Skeleton className="h-36 rounded-xl lg:col-span-4" />
      <Skeleton className="h-36 rounded-xl lg:col-span-4" />
      <Skeleton className="h-44 rounded-xl lg:col-span-8" />
      <Skeleton className="h-44 rounded-xl lg:col-span-4" />
      <Skeleton className="h-80 rounded-xl lg:col-span-12" />
    </div>
  );
}

/** Tela Início (seção 12.5), em grade de 12 colunas. */
export function Inicio() {
  const { cultivoId } = useParams();
  const resumo = useResumo(Number(cultivoId));

  if (resumo.isPending) return <Carregando />;
  if (resumo.error) {
    if (resumo.error instanceof ErroApi && resumo.error.status === 404) return <NaoEncontrada />;
    return (
      <EstadoVazio
        icone={AlertCircle}
        titulo="Não foi possível carregar"
        texto={mensagemDeErro(resumo.error)}
        acao={
          <Button variant="outline" onClick={() => resumo.refetch()}>
            <RefreshCw className="size-4" /> Tentar de novo
          </Button>
        }
      />
    );
  }

  const r = resumo.data;
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold">{r.cultivo.nome}</h1>
        <p className="text-sm text-muted-foreground">
          {r.cultivo.cultura_info?.nome ?? r.cultivo.cultura} · {r.cultivo.fazenda.nome}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <CardLamina resumo={r} />
        </div>
        <div className="lg:col-span-5">
          <CardEstado resumo={r} />
        </div>

        <div className="grid gap-4 sm:grid-cols-3 lg:col-span-12">
          <CardFase resumo={r} />
          <CardSolo resumo={r} />
          <CardDemanda resumo={r} />
        </div>

        <div className="lg:col-span-8">
          <CardClima resumo={r} />
        </div>
        <div className="lg:col-span-4">
          <CardValvula resumo={r} />
        </div>

        <div className="lg:col-span-12">
          <GraficoSemana dias={r.ultimos_7_dias} />
        </div>
      </div>
    </div>
  );
}
