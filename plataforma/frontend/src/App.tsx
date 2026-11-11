import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router-dom";

import { criarClienteQuery } from "@/api/consultas";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ProvedorTema } from "@/hooks/useTema";
import { roteador } from "@/rotas";

export default function App() {
  const [clienteQuery] = useState(criarClienteQuery);
  return (
    <ProvedorTema>
      <QueryClientProvider client={clienteQuery}>
        <TooltipProvider delayDuration={200}>
          <RouterProvider router={roteador} />
          <Toaster position="top-center" richColors closeButton />
        </TooltipProvider>
      </QueryClientProvider>
    </ProvedorTema>
  );
}
