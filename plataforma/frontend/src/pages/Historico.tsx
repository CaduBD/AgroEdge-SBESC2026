import { AlertCircle, CalendarSearch, Download, Loader2, RefreshCw } from "lucide-react";
import { useParams, useSearchParams } from "react-router-dom";

import { ErroApi, mensagemDeErro } from "@/api/cliente";
import { useDiarios, useIrrigacoes, useLeituras, useResumo } from "@/api/consultas";
import { EstadoVazio } from "@/components/EstadoVazio";
import { AbaClima } from "@/components/historico/AbaClima";
import { AbaFechamentos } from "@/components/historico/AbaFechamentos";
import { AbaIrrigacoes } from "@/components/historico/AbaIrrigacoes";
import { FiltroPeriodo, SeletorVariaveis } from "@/components/historico/Filtros";
import { PADRAO, VARIAVEIS } from "@/components/historico/variaveis";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { dataCompleta } from "@/lib/formatar";
import { diasNoPeriodo, limitesUnix, resolverPeriodo, type TipoPeriodo } from "@/lib/periodo";
import { NaoEncontrada } from "@/pages/NaoEncontrada";

type Aba = "clima" | "fechamentos" | "irrigacoes";
const ABAS: Aba[] = ["clima", "fechamentos", "irrigacoes"];
const TIPO_CSV: Record<Aba, string> = {
  clima: "leituras",
  fechamentos: "diarios",
  irrigacoes: "irrigacoes",
};

function Carregando() {
  return (
    <div className="grid gap-4">
      <Skeleton className="h-72 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

function Erro({ erro, tentar }: { erro: unknown; tentar: () => void }) {
  if (erro instanceof ErroApi && erro.status === 404) return <NaoEncontrada />;
  return (
    <EstadoVazio
      icone={AlertCircle}
      titulo="Não foi possível carregar"
      texto={mensagemDeErro(erro)}
      acao={
        <Button variant="outline" onClick={tentar}>
          <RefreshCw className="size-4" /> Tentar de novo
        </Button>
      }
    />
  );
}

/** Tela Histórico (seção 12.5): filtros na URL, abas Clima | Fechamentos | Irrigações. */
export function Historico() {
  const { cultivoId: idTexto } = useParams();
  const cultivoId = Number(idTexto);
  const [params, setParams] = useSearchParams();
  const resumo = useResumo(cultivoId);

  const periodo = resolverPeriodo(
    params.get("periodo"),
    params.get("de"),
    params.get("ate"),
    resumo.data?.cultivo.data_referencia,
  );
  const aba: Aba = ABAS.includes(params.get("aba") as Aba) ? (params.get("aba") as Aba) : "clima";
  const pedidas = (params.get("variaveis") ?? "")
    .split(",")
    .filter((v) => VARIAVEIS.some((x) => x.chave === v));
  const variaveis = pedidas.length ? pedidas : PADRAO;

  const atualizar = (mudancas: Record<string, string | null>) => {
    const novos = new URLSearchParams(params);
    for (const [k, v] of Object.entries(mudancas)) {
      if (v === null) novos.delete(k);
      else novos.set(k, v);
    }
    setParams(novos, { replace: true });
  };
  const mudarPeriodo = (tipo: TipoPeriodo, de?: string, ate?: string) =>
    atualizar({ periodo: tipo, de: de ?? null, ate: ate ?? null });

  const leituras = useLeituras(cultivoId, periodo.de, periodo.ate, variaveis);
  const diarios = useDiarios(cultivoId, periodo.de, periodo.ate);
  const irrigacoes = useIrrigacoes(cultivoId, periodo.de, periodo.ate);
  const atual = { clima: leituras, fechamentos: diarios, irrigacoes }[aba];

  const csv = `/api/cultivos/${cultivoId}/exportar.csv?${new URLSearchParams({
    tipo: TIPO_CSV[aba],
    de: periodo.de,
    ate: periodo.ate,
  })}`;

  // Na aba Irrigações, "nenhuma irrigação" já aparece no gráfico e na tabela.
  const semDados =
    (aba === "clima" && leituras.data?.pontos.length === 0) ||
    (aba === "fechamentos" && diarios.data?.length === 0);

  const ampliar =
    periodo.tipo === "7d" ? (
      <Button variant="outline" onClick={() => mudarPeriodo("30d")}>
        Ver os últimos 30 dias
      </Button>
    ) : periodo.tipo !== "ciclo" ? (
      <Button variant="outline" onClick={() => mudarPeriodo("ciclo")}>
        Ver o ciclo inteiro
      </Button>
    ) : undefined;

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Histórico</h1>
          <p className="text-sm text-muted-foreground">
            {resumo.data?.cultivo.nome ?? "…"} · {dataCompleta(`${periodo.de}T12:00:00Z`)} a{" "}
            {dataCompleta(`${periodo.ate}T12:00:00Z`)} ({diasNoPeriodo(periodo)} dias)
          </p>
        </div>
        <Button variant="outline" asChild>
          <a href={csv} download>
            <Download className="size-4" />
            Exportar CSV
          </a>
        </Button>
      </div>

      <Tabs value={aba} onValueChange={(v) => atualizar({ aba: v })} className="gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <FiltroPeriodo periodo={periodo} aoMudar={mudarPeriodo} />
          <div className="flex items-center gap-2">
            {atual.isFetching && !atual.isPending && (
              <Loader2
                className="size-4 animate-spin text-muted-foreground"
                aria-label="Atualizando"
              />
            )}
            {aba === "clima" && (
              <SeletorVariaveis
                selecionadas={variaveis}
                aoMudar={(v) => atualizar({ variaveis: v.join(",") })}
              />
            )}
            <TabsList>
              <TabsTrigger value="clima">Clima</TabsTrigger>
              <TabsTrigger value="fechamentos">Fechamentos</TabsTrigger>
              <TabsTrigger value="irrigacoes">Irrigações</TabsTrigger>
            </TabsList>
          </div>
        </div>

        {atual.isPending ? (
          <Carregando />
        ) : atual.error ? (
          <Erro erro={atual.error} tentar={() => atual.refetch()} />
        ) : semDados ? (
          <EstadoVazio
            icone={CalendarSearch}
            titulo="Sem dados neste período"
            texto="A placa não enviou dados para este cultivo nas datas escolhidas."
            acao={ampliar}
          />
        ) : (
          <>
            <TabsContent value="clima">
              {leituras.data && <AbaClima serie={leituras.data} dominio={limitesUnix(periodo)} />}
            </TabsContent>
            <TabsContent value="fechamentos">
              {diarios.data && <AbaFechamentos diarios={diarios.data} />}
            </TabsContent>
            <TabsContent value="irrigacoes">
              {irrigacoes.data && <AbaIrrigacoes irrigacoes={irrigacoes.data} periodo={periodo} />}
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
}
