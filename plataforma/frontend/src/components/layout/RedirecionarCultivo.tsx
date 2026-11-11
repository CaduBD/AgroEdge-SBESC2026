import { Sprout } from "lucide-react";
import { Link, Navigate } from "react-router-dom";

import { EstadoVazio } from "@/components/EstadoVazio";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCultivoSelecionado } from "@/hooks/useCultivoSelecionado";

/** "/" e "/historico": abrem o último cultivo usado (ou o primeiro). */
export function RedirecionarCultivo({ pagina }: { pagina: "inicio" | "historico" }) {
  const { cultivoId, carregando, grupos } = useCultivoSelecionado();

  if (carregando) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-32 rounded-xl" />
      </div>
    );
  }
  if (cultivoId) return <Navigate to={`/cultivos/${cultivoId}/${pagina}`} replace />;

  const semFazenda = grupos.length === 0;
  return (
    <EstadoVazio
      icone={Sprout}
      titulo={semFazenda ? "Crie sua primeira fazenda" : "Cadastre seu primeiro cultivo"}
      texto={
        semFazenda
          ? "Comece cadastrando a fazenda e depois o cultivo onde a placa vai ficar."
          : "Cadastre um cultivo e instale a placa nele para ver os dados aqui."
      }
      acao={
        <Button asChild>
          <Link to="/cultivos">Ir para Cultivos</Link>
        </Button>
      }
    />
  );
}
