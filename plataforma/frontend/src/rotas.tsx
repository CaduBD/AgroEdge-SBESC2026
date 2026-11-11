import { createBrowserRouter, Navigate } from "react-router-dom";

import { Layout } from "@/components/layout/Layout";
import { Protegido } from "@/components/layout/Protegido";
import { RedirecionarCultivo } from "@/components/layout/RedirecionarCultivo";
import { Conta } from "@/pages/Conta";
import { Dispositivo } from "@/pages/Dispositivo";
import { CultivoEditar } from "@/pages/CultivoEditar";
import { Cultivos } from "@/pages/Cultivos";
import { Historico } from "@/pages/Historico";
import { Inicio } from "@/pages/Inicio";
import { Login } from "@/pages/Login";
import { NaoEncontrada } from "@/pages/NaoEncontrada";

export const roteador = createBrowserRouter([
  { path: "/login", element: <Login /> },
  {
    element: <Protegido />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <RedirecionarCultivo pagina="inicio" /> },
          { path: "historico", element: <RedirecionarCultivo pagina="historico" /> },
          { path: "cultivos/:cultivoId/inicio", element: <Inicio /> },
          {
            path: "cultivos/:cultivoId/historico",
            element: <Historico />,
          },
          { path: "cultivos", element: <Cultivos /> },
          { path: "cultivos/novo", element: <CultivoEditar /> },
          { path: "cultivos/:cultivoId/editar", element: <CultivoEditar key="editar" /> },
          { path: "dispositivo", element: <Dispositivo /> },
          { path: "conta", element: <Conta /> },
          { path: "inicio", element: <Navigate to="/" replace /> },
          { path: "*", element: <NaoEncontrada /> },
        ],
      },
    ],
  },
]);
