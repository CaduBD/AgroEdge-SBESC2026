/** Estado "sem conexão com o servidor" para o banner discreto (seção 12.6). */
import { useSyncExternalStore } from "react";

let conectado = true;
const ouvintes = new Set<() => void>();

export function definirConexao(valor: boolean) {
  if (valor === conectado) return;
  conectado = valor;
  ouvintes.forEach((ouvir) => ouvir());
}

export function useConectado(): boolean {
  return useSyncExternalStore(
    (ouvir) => {
      ouvintes.add(ouvir);
      return () => ouvintes.delete(ouvir);
    },
    () => conectado,
  );
}
