import { TZDate } from "@date-fns/tz";
import { format } from "date-fns";
import { AlertTriangle, Loader2, MapPin } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { mensagemDeErro } from "@/api/cliente";
import { useFazendasComCultivos, useInstalar } from "@/api/consultas";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FUSO } from "@/lib/formatar";

const agoraLocal = () => format(new TZDate(new Date(), FUSO), "yyyy-MM-dd'T'HH:mm");

/** "Instalar em outro cultivo": escolhe o cultivo e o início (padrão: agora). */
export function DialogoInstalar({
  serial,
  cultivoAtual,
}: {
  serial: string;
  cultivoAtual: number | null;
}) {
  const [aberto, setAberto] = useState(false);
  const [cultivoId, setCultivoId] = useState("");
  const [inicio, setInicio] = useState(agoraLocal);
  const { grupos } = useFazendasComCultivos();
  const instalar = useInstalar(serial);

  // Cultivo com outra placa não pode receber esta (uma placa por cultivo).
  const opcoes = grupos.map((g) => ({
    fazenda: g.fazenda,
    cultivos: g.cultivos.filter((c) => c.id !== cultivoAtual),
  }));
  const noPassado = inicio < agoraLocal();

  const enviar = () => {
    // datetime-local está no fuso de Petrolina; o backend recebe em UTC.
    const inicioUtc = new TZDate(`${inicio}:00`, FUSO).toISOString();
    instalar.mutate(
      { cultivo_id: Number(cultivoId), inicio: inicioUtc },
      {
        onSuccess: (inst) => {
          toast.success(`Placa instalada em “${inst.cultivo_nome}”. Configuração enviada.`);
          setAberto(false);
        },
        onError: (e) => toast.error(mensagemDeErro(e)),
      },
    );
  };

  return (
    <Dialog
      open={aberto}
      onOpenChange={(a) => {
        setAberto(a);
        if (a) {
          setCultivoId("");
          setInicio(agoraLocal());
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <MapPin className="size-4" />
          {cultivoAtual ? "Instalar em outro cultivo" : "Instalar em um cultivo"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Instalar a placa {serial}</DialogTitle>
          <DialogDescription>
            A placa recebe a configuração do cultivo escolhido e começa um histórico novo nele.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="cultivo-destino">Cultivo</Label>
            <Select value={cultivoId} onValueChange={setCultivoId}>
              <SelectTrigger id="cultivo-destino" className="w-full">
                <SelectValue placeholder="Escolha o cultivo" />
              </SelectTrigger>
              <SelectContent>
                {opcoes
                  .filter((g) => g.cultivos.length)
                  .map((g) => (
                    <SelectGroup key={g.fazenda.id}>
                      <SelectLabel>{g.fazenda.nome}</SelectLabel>
                      {g.cultivos.map((c) => (
                        <SelectItem
                          key={c.id}
                          value={String(c.id)}
                          disabled={!!c.configuracao && c.configuracao.serial !== serial}
                        >
                          {c.nome}
                          {c.configuracao && c.configuracao.serial !== serial && (
                            <span className="text-muted-foreground">
                              {" "}
                              · já tem a {c.configuracao.serial}
                            </span>
                          )}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="inicio-instalacao">Instalada desde</Label>
            <Input
              id="inicio-instalacao"
              type="datetime-local"
              value={inicio}
              max={agoraLocal()}
              onChange={(e) => setInicio(e.target.value)}
            />
            {noPassado && (
              <p className="flex items-start gap-1.5 text-xs text-estado-moderado">
                <AlertTriangle className="mt-px size-3.5 shrink-0" />
                Início no passado: as leituras desde essa hora passam para o novo cultivo.
              </p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setAberto(false)}>
            Voltar
          </Button>
          <Button onClick={enviar} disabled={!cultivoId || !inicio || instalar.isPending}>
            {instalar.isPending && <Loader2 className="size-4 animate-spin" />}
            Instalar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
