import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useEu } from "@/api/consultas";
import { Logo } from "@/components/Logo";

/** Só deixa passar com sessão válida; senão, vai para o login. */
export function Protegido() {
  const eu = useEu();
  const local = useLocation();

  if (eu.isPending) {
    return (
      <div className="grid min-h-svh place-items-center">
        <Logo className="animate-pulse" />
      </div>
    );
  }
  if (!eu.data) {
    return <Navigate to="/login" replace state={{ de: local.pathname }} />;
  }
  return <Outlet />;
}
