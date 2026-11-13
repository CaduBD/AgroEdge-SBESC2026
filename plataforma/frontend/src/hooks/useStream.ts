/**
 * Tempo real (seção 11): assina GET /api/stream (SSE) e, a cada evento, invalida as
 * consultas afetadas para o TanStack Query buscar de novo. Alguns eventos geram toast.
 *
 * - Invalidações são agrupadas (o envio do atrasado do buffer gera muitos eventos seguidos).
 * - O EventSource reconecta sozinho em quedas de rede; se a conexão for encerrada (ex.: 401),
 *   tentamos de novo com espera crescente. Ao reconectar, tudo é atualizado, porque eventos
 *   perdidos durante a queda não voltam.
 */
import { type QueryClient, type QueryKey, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";

import { chaves } from "@/api/consultas";
import type { Cultivo, Fazenda } from "@/api/tipos";
import { numero } from "@/lib/formatar";
import { RESULTADO_COMANDO } from "@/lib/rotulos";
import { avisarUmaVez, idToastConfig } from "@/lib/toasts";

interface DadosEvento {
  serial: string;
  cultivo_id: number | null;
  [campo: string]: unknown;
}

const AGRUPAR_MS = 800;
const ESPERA_MAX_MS = 30_000;
const OCULTA_MS = 15_000; // tolera trocar de aba rapidamente sem reconectar
// O servidor manda `ping` a cada 25 s. Silêncio maior que isto = conexão "zumbi" (comum atrás
// de proxies quando o backend reinicia): fecha e reconecta.
const SILENCIO_MAX_MS = 60_000;

/** Fila de invalidações: junta chaves repetidas e aplica de uma vez. */
function criarFila(qc: QueryClient) {
  const pendentes = new Map<string, QueryKey>();
  let timer: number | undefined;
  return {
    add(chave: QueryKey) {
      pendentes.set(JSON.stringify(chave), chave);
      timer ??= window.setTimeout(() => {
        pendentes.forEach((k) => qc.invalidateQueries({ queryKey: k }));
        pendentes.clear();
        timer = undefined;
      }, AGRUPAR_MS);
    },
    cancelar() {
      window.clearTimeout(timer);
    },
  };
}

/** Nome do cultivo a partir do cache (para toasts que digam de qual cultivo se trata). */
function nomeDoCultivo(qc: QueryClient, cultivoId: number | null): string | null {
  if (cultivoId == null) return null;
  const fazendas = qc.getQueryData<Fazenda[]>(chaves.fazendas) ?? [];
  for (const f of fazendas) {
    const c = qc.getQueryData<Cultivo[]>(chaves.cultivos(f.id))?.find((x) => x.id === cultivoId);
    if (c) return c.nome;
  }
  return null;
}

function tratar(qc: QueryClient, fila: ReturnType<typeof criarFila>, tipo: string, d: DadosEvento) {
  const cid = d.cultivo_id;
  const cultivo = (sub: string) => cid != null && fila.add(["cultivos", cid, sub]);
  const dispositivo = () => fila.add(["dispositivos", d.serial]);
  const nome = nomeDoCultivo(qc, cid);
  const de = nome ? ` · ${nome}` : "";

  switch (tipo) {
    case "leitura":
      cultivo("resumo");
      cultivo("leituras");
      dispositivo();
      break;
    case "diario": {
      cultivo("resumo");
      cultivo("diarios");
      const lamina = Number(d.lamina_bruta ?? 0);
      toast.info(
        lamina > 0
          ? `Novo fechamento${de}: irrigar ${numero(lamina)} mm`
          : `Novo fechamento${de}: sem irrigação necessária`,
        { description: d.minutos ? `${numero(Number(d.minutos), 0)} min de válvula` : undefined },
      );
      break;
    }
    case "irrigacao":
      cultivo("resumo");
      cultivo("irrigacoes");
      dispositivo();
      break;
    case "status":
      cultivo("resumo");
      dispositivo();
      break;
    case "config_aplicada":
      cultivo("resumo");
      fila.add(["fazendas"]); // listas de cultivos trazem o estado da configuração
      if (cid != null) fila.add(["cultivos", cid]);
      dispositivo();
      // Mesmo aviso da tela (EstadoConfiguracao): sai uma vez só, venha de onde vier.
      {
        const id = idToastConfig(Number(d.instalacao_id), Number(d.cfg_v));
        avisarUmaVez(id, () =>
          toast.success(`Configuração v${d.cfg_v} aplicada na placa${de}`, { id }),
        );
      }
      break;
    case "comando": {
      cultivo("resumo");
      fila.add(chaves.comandos(d.serial));
      const resultado = typeof d.resultado === "string" ? d.resultado : null;
      if (d.estado === "executado") toast.success(RESULTADO_COMANDO.executado);
      else if (d.estado === "expirado" && resultado)
        // Resposta tardia: a placa voltou e respondeu a um comando que já tinha expirado.
        toast.info(`A placa voltou: ${RESULTADO_COMANDO[resultado] ?? resultado}.`);
      else if (d.estado === "expirado") toast.warning("O comando expirou sem resposta da placa.");
      else if (resultado) toast.error(RESULTADO_COMANDO[resultado] ?? `Comando: ${resultado}`);
      break;
    }
  }
}

const TIPOS = ["leitura", "diario", "irrigacao", "status", "config_aplicada", "comando"];

export function useStream(ativo: boolean) {
  const qc = useQueryClient();

  useEffect(() => {
    if (!ativo) return;
    const fila = criarFila(qc);
    let fonte: EventSource | null = null;
    let espera = 1000;
    let retentativa: number | undefined;
    let jaAbriu = false;
    let encerrado = false;
    let vigia: number | undefined;

    const renovarVigia = () => {
      window.clearTimeout(vigia);
      vigia = window.setTimeout(() => {
        desconectar();
        conectar();
      }, SILENCIO_MAX_MS);
    };

    const conectar = () => {
      fonte = new EventSource("/api/stream", { withCredentials: true });
      renovarVigia();
      fonte.addEventListener("ping", renovarVigia);
      fonte.onopen = () => {
        renovarVigia();
        espera = 1000;
        // Reconexão: eventos perdidos durante a queda não voltam; atualiza tudo.
        if (jaAbriu) qc.invalidateQueries();
        jaAbriu = true;
      };
      fonte.onerror = () => {
        // CONNECTING: o navegador já está tentando de novo. CLOSED: desistiu (ex.: 401).
        if (fonte?.readyState === EventSource.CLOSED && !encerrado) {
          fonte.close();
          retentativa = window.setTimeout(conectar, espera);
          espera = Math.min(espera * 2, ESPERA_MAX_MS);
        }
      };
      for (const tipo of TIPOS) {
        fonte.addEventListener(tipo, (e) => {
          renovarVigia();
          try {
            tratar(qc, fila, tipo, JSON.parse((e as MessageEvent).data) as DadosEvento);
          } catch {
            /* evento malformado: ignora */
          }
        });
      }
    };

    const desconectar = () => {
      window.clearTimeout(retentativa);
      window.clearTimeout(vigia);
      fonte?.close();
      fonte = null;
    };

    // Aba em segundo plano solta a conexão: o navegador só abre 6 conexões por servidor
    // (HTTP/1.1), e cada aba com o painel prenderia uma. Ao voltar, reconecta e atualiza tudo.
    let timerOculta: number | undefined;
    const aoMudarVisibilidade = () => {
      if (document.visibilityState === "hidden") {
        timerOculta = window.setTimeout(desconectar, OCULTA_MS);
      } else {
        window.clearTimeout(timerOculta);
        if (!fonte) {
          espera = 1000;
          conectar();
        }
      }
    };
    document.addEventListener("visibilitychange", aoMudarVisibilidade);

    if (document.visibilityState !== "hidden") conectar();
    return () => {
      encerrado = true;
      fila.cancelar();
      window.clearTimeout(timerOculta);
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
      desconectar();
    };
  }, [ativo, qc]);
}
