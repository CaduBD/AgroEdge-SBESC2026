import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Monitor, Moon, Sun } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { mensagemDeErro } from "@/api/cliente";
import { useEu, useTrocarSenha } from "@/api/consultas";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type PreferenciaTema, useTema } from "@/hooks/useTema";
import { cn } from "@/lib/utils";

const esquema = z
  .object({
    senha_atual: z.string().min(1, "Informe a senha atual"),
    senha_nova: z.string().min(8, "A nova senha precisa de pelo menos 8 caracteres"),
    confirmacao: z.string(),
  })
  .refine((d) => d.senha_nova === d.confirmacao, {
    message: "As senhas não conferem",
    path: ["confirmacao"],
  });
type Dados = z.infer<typeof esquema>;

const TEMAS: { valor: PreferenciaTema; rotulo: string; icone: typeof Sun }[] = [
  { valor: "sistema", rotulo: "Sistema", icone: Monitor },
  { valor: "claro", rotulo: "Claro", icone: Sun },
  { valor: "escuro", rotulo: "Escuro", icone: Moon },
];

export function Conta() {
  const { data: usuario } = useEu();
  const { preferencia, definir } = useTema();
  const trocar = useTrocarSenha();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<Dados>({ resolver: zodResolver(esquema) });

  const salvar = ({ senha_atual, senha_nova }: Dados) =>
    trocar.mutate(
      { senha_atual, senha_nova },
      {
        onSuccess: () => {
          toast.success("Senha alterada.");
          reset();
        },
        onError: (e) => toast.error(mensagemDeErro(e)),
      },
    );

  return (
    <div className="grid max-w-2xl gap-6">
      <h1 className="text-2xl font-semibold">Conta</h1>

      <Card>
        <CardHeader>
          <CardTitle>Seus dados</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-muted-foreground">Nome</p>
            <p className="font-medium">{usuario?.nome}</p>
          </div>
          <div>
            <p className="text-muted-foreground">E-mail</p>
            <p className="font-medium">{usuario?.email}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tema</CardTitle>
          <CardDescription>Por padrão, segue o tema do seu aparelho.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Tema">
            {TEMAS.map(({ valor, rotulo, icone: Icone }) => (
              <button
                key={valor}
                type="button"
                role="radio"
                aria-checked={preferencia === valor}
                onClick={() => definir(valor)}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors",
                  preferencia === valor
                    ? "border-primary bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                <Icone className="size-5" />
                {rotulo}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Trocar senha</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(salvar)} className="grid gap-4 sm:max-w-sm" noValidate>
            {(
              [
                ["senha_atual", "Senha atual", "current-password"],
                ["senha_nova", "Nova senha", "new-password"],
                ["confirmacao", "Repita a nova senha", "new-password"],
              ] as const
            ).map(([campo, rotulo, auto]) => (
              <div key={campo} className="grid gap-2">
                <Label htmlFor={campo}>{rotulo}</Label>
                <Input
                  id={campo}
                  type="password"
                  autoComplete={auto}
                  aria-invalid={!!errors[campo]}
                  {...register(campo)}
                />
                {errors[campo] && (
                  <p className="text-xs text-destructive">{errors[campo]?.message}</p>
                )}
              </div>
            ))}
            <Button type="submit" className="w-fit" disabled={trocar.isPending}>
              {trocar.isPending && <Loader2 className="size-4 animate-spin" />}
              Salvar nova senha
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
