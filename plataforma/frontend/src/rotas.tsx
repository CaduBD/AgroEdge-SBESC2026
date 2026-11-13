import { createBrowserRouter, Navigate } from "react-router-dom";

import { Layout } from "@/components/layout/Layout";
import { Protegido } from "@/components/layout/Protegido";
import { RedirecionarCultivo } from "@/components/layout/RedirecionarCultivo";
import { Inicio } from "@/pages/Inicio";
import { NaoEncontrada } from "@/pages/NaoEncontrada";

// Telas carregadas só quando abertas (cada uma vira um arquivo separado no build). O Início
// fica no arquivo principal: é a tela que o produtor mais abre, e no celular.
const carregarHistorico = async () => ({
  Component: (await import("@/pages/Historico")).Historico,
});
const carregarCultivos = async () => ({ Component: (await import("@/pages/Cultivos")).Cultivos });
const carregarCultivoEditar = async () => ({
  Component: (await import("@/pages/CultivoEditar")).CultivoEditar,
});
const carregarDispositivo = async () => ({
  Component: (await import("@/pages/Dispositivo")).Dispositivo,
});
const carregarConta = async () => ({ Component: (await import("@/pages/Conta")).Conta });
const carregarLogin = async () => ({ Component: (await import("@/pages/Login")).Login });

export const roteador = createBrowserRouter([
  { path: "/login", lazy: carregarLogin },
  {
    element: <Protegido />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <RedirecionarCultivo pagina="inicio" /> },
          { path: "historico", element: <RedirecionarCultivo pagina="historico" /> },
          { path: "cultivos/:cultivoId/inicio", element: <Inicio /> },
          { path: "cultivos/:cultivoId/historico", lazy: carregarHistorico },
          { path: "cultivos", lazy: carregarCultivos },
          { path: "cultivos/novo", lazy: carregarCultivoEditar },
          { path: "cultivos/:cultivoId/editar", lazy: carregarCultivoEditar },
          { path: "dispositivo", lazy: carregarDispositivo },
          { path: "conta", lazy: carregarConta },
          { path: "inicio", element: <Navigate to="/" replace /> },
          { path: "*", element: <NaoEncontrada /> },
        ],
      },
    ],
  },
]);
