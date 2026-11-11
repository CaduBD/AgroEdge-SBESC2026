/**
 * Cultivo selecionado: vale para Início e Histórico. Fica na URL (/cultivos/:id/…) e no
 * navegador, para voltar ao mesmo cultivo da próxima vez (seção 12.4).
 */
import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { useFazendasComCultivos } from "@/api/consultas";
import type { Cultivo, Fazenda } from "@/api/tipos";

const CHAVE = "agroedge.cultivo";

export function lerCultivoSalvo(): number | null {
  try {
    const valor = Number(localStorage.getItem(CHAVE));
    return Number.isInteger(valor) && valor > 0 ? valor : null;
  } catch {
    return null;
  }
}

export function salvarCultivo(id: number) {
  try {
    localStorage.setItem(CHAVE, String(id));
  } catch {
    /* ignora */
  }
}

export interface Selecao {
  cultivoId: number | null;
  cultivo: Cultivo | null;
  fazenda: Fazenda | null;
  carregando: boolean;
  grupos: { fazenda: Fazenda; cultivos: Cultivo[] }[];
}

export function useCultivoSelecionado(): Selecao {
  const params = useParams();
  const { grupos, carregando } = useFazendasComCultivos();
  const daUrl = params.cultivoId ? Number(params.cultivoId) : null;
  const todos = grupos.flatMap((g) => g.cultivos.map((c) => ({ cultivo: c, fazenda: g.fazenda })));

  const salvo = lerCultivoSalvo();
  const escolhido =
    todos.find((t) => t.cultivo.id === daUrl) ??
    (daUrl ? undefined : (todos.find((t) => t.cultivo.id === salvo) ?? todos[0]));

  useEffect(() => {
    if (daUrl) salvarCultivo(daUrl);
  }, [daUrl]);

  return {
    cultivoId: escolhido?.cultivo.id ?? daUrl,
    cultivo: escolhido?.cultivo ?? null,
    fazenda: escolhido?.fazenda ?? null,
    carregando,
    grupos,
  };
}
