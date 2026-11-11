import { zodResolver } from "@hookform/resolvers/zod";
import { Droplets, Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ErroApi, mensagemDeErro } from "@/api/cliente";
import { useEu, useLogin } from "@/api/consultas";
import { Logo } from "@/components/Logo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const esquema = z.object({
  email: z.string().trim().min(1, "Informe o e-mail"),
  senha: z.string().min(1, "Informe a senha"),
});
type Dados = z.infer<typeof esquema>;

export function Login() {
  const eu = useEu();
  const login = useLogin();
  const navegar = useNavigate();
  const local = useLocation();
  const destino = (local.state as { de?: string } | null)?.de ?? "/";

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Dados>({ resolver: zodResolver(esquema) });

  if (eu.data) return <Navigate to={destino} replace />;

  const entrar = (dados: Dados) =>
    login.mutate(dados, { onSuccess: () => navegar(destino, { replace: true }) });

  const erro =
    login.error instanceof ErroApi && login.error.status === 401
      ? "E-mail ou senha incorretos."
      : login.error
        ? mensagemDeErro(login.error)
        : null;

  return (
    <div className="relative grid min-h-svh place-items-center overflow-hidden px-4 py-10">
      {/* Fundo discreto: gradiente da cor primária */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_50%_-10%,color-mix(in_oklab,var(--primary)_14%,transparent),transparent)]"
      />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-xl">Entrar</CardTitle>
            <CardDescription>Irrigação de precisão no Vale do São Francisco.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(entrar)} className="grid gap-4" noValidate>
              {erro && (
                <Alert variant="destructive">
                  <AlertDescription>{erro}</AlertDescription>
                </Alert>
              )}
              <div className="grid gap-2">
                <Label htmlFor="email">E-mail</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  aria-invalid={!!errors.email}
                  {...register("email")}
                />
                {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="senha">Senha</Label>
                <Input
                  id="senha"
                  type="password"
                  autoComplete="current-password"
                  aria-invalid={!!errors.senha}
                  {...register("senha")}
                />
                {errors.senha && <p className="text-xs text-destructive">{errors.senha.message}</p>}
              </div>
              <Button type="submit" className="mt-2 w-full" disabled={login.isPending}>
                {login.isPending && <Loader2 className="size-4 animate-spin" />}
                Entrar
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <Droplets className="size-3.5" /> AgroEdge · SBESC 2026 · UNIVASF
        </p>
      </div>
    </div>
  );
}
