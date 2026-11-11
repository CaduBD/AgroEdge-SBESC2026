import { MapPinOff } from "lucide-react";
import { Link } from "react-router-dom";

import { EstadoVazio } from "@/components/EstadoVazio";
import { Button } from "@/components/ui/button";

export function NaoEncontrada() {
  return (
    <EstadoVazio
      icone={MapPinOff}
      titulo="Página não encontrada"
      texto="O endereço não existe ou o recurso não é seu."
      acao={
        <Button asChild>
          <Link to="/">Voltar ao início</Link>
        </Button>
      }
    />
  );
}
