import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { mensagemDeErro } from "@/api/cliente";
import { useSalvarFazenda } from "@/api/consultas";
import type { Fazenda } from "@/api/tipos";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Criar ou renomear uma fazenda. */
export function DialogoFazenda({
  aberto,
  aoMudar,
  fazenda,
}: {
  aberto: boolean;
  aoMudar: (a: boolean) => void;
  fazenda?: Fazenda | null;
}) {
  const salvar = useSalvarFazenda();
  const [nome, setNome] = useState(fazenda?.nome ?? "");
  const [municipio, setMunicipio] = useState(fazenda?.municipio ?? "");

  const enviar = (e: React.FormEvent) => {
    e.preventDefault();
    salvar.mutate(
      { id: fazenda?.id, nome: nome.trim(), municipio: municipio.trim() || null },
      {
        onSuccess: () => {
          toast.success(fazenda ? "Fazenda atualizada." : "Fazenda criada.");
          aoMudar(false);
        },
        onError: (erro) => toast.error(mensagemDeErro(erro)),
      },
    );
  };

  return (
    <Dialog
      open={aberto}
      onOpenChange={(a) => {
        if (a) {
          setNome(fazenda?.nome ?? "");
          setMunicipio(fazenda?.municipio ?? "");
        }
        aoMudar(a);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <form onSubmit={enviar} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{fazenda ? "Editar fazenda" : "Nova fazenda"}</DialogTitle>
            <DialogDescription>
              Cada fazenda agrupa os cultivos onde as placas podem ser instaladas.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="fazenda-nome">Nome</Label>
            <Input
              id="fazenda-nome"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Fazenda Boa Vista"
              autoFocus
              required
              maxLength={100}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="fazenda-municipio">Município (opcional)</Label>
            <Input
              id="fazenda-municipio"
              value={municipio}
              onChange={(e) => setMunicipio(e.target.value)}
              placeholder="Ex.: Petrolina - PE"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => aoMudar(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!nome.trim() || salvar.isPending}>
              {salvar.isPending && <Loader2 className="size-4 animate-spin" />}
              Salvar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
