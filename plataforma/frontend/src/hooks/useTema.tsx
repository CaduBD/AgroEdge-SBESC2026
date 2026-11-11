import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type PreferenciaTema = "sistema" | "claro" | "escuro";
type TemaEfetivo = "light" | "dark";

const CHAVE = "agroedge.tema";

interface ContextoTema {
  preferencia: PreferenciaTema;
  temaEfetivo: TemaEfetivo;
  definir: (p: PreferenciaTema) => void;
}

const Contexto = createContext<ContextoTema | null>(null);

function lerPreferencia(): PreferenciaTema {
  try {
    const salvo = localStorage.getItem(CHAVE);
    if (salvo === "claro" || salvo === "escuro" || salvo === "sistema") return salvo;
  } catch {
    /* sem localStorage: segue o sistema */
  }
  return "sistema";
}

const consultaEscuro = () => window.matchMedia("(prefers-color-scheme: dark)");

/** Tema claro/escuro: segue o sistema por padrão; a escolha fica no navegador. */
export function ProvedorTema({ children }: { children: React.ReactNode }) {
  const [preferencia, setPreferencia] = useState<PreferenciaTema>(lerPreferencia);
  const [sistemaEscuro, setSistemaEscuro] = useState(() => consultaEscuro().matches);

  useEffect(() => {
    const mq = consultaEscuro();
    const ouvir = (e: MediaQueryListEvent) => setSistemaEscuro(e.matches);
    mq.addEventListener("change", ouvir);
    return () => mq.removeEventListener("change", ouvir);
  }, []);

  const temaEfetivo: TemaEfetivo =
    preferencia === "escuro" || (preferencia === "sistema" && sistemaEscuro) ? "dark" : "light";

  useEffect(() => {
    document.documentElement.classList.toggle("dark", temaEfetivo === "dark");
  }, [temaEfetivo]);

  const definir = useCallback((p: PreferenciaTema) => {
    setPreferencia(p);
    try {
      localStorage.setItem(CHAVE, p);
    } catch {
      /* ignora */
    }
  }, []);

  const valor = useMemo(
    () => ({ preferencia, temaEfetivo, definir }),
    [preferencia, temaEfetivo, definir],
  );
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTema(): ContextoTema {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("useTema fora do ProvedorTema");
  return ctx;
}
