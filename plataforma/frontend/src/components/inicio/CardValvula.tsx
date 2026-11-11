import { CalendarClock, History, Loader2, Power, PowerOff, Waves } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { mensagemDeErro } from "@/api/cliente";
import { useEnviarComando } from "@/api/consultas";
import type { Resumo } from "@/api/tipos";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAgora } from "@/hooks/useAgora";
import { diaHora, diaMes, duracao, hora, mm, minutos, noFuso } from "@/lib/formatar";
import { ORIGEM_IRRIGACAO } from "@/lib/rotulos";

import { Rotulo } from "./Cards";

function quando(iso: string, agora: Date): string {
  const alvo = noFuso(iso);
  const hoje = noFuso(agora);
  const amanha = noFuso(new Date(agora.getTime() + 86_400_000));
  if (alvo.toDateString() === hoje.toDateString()) return `Hoje às ${hora(iso)}`;
  if (alvo.toDateString() === amanha.toDateString()) return `Amanhã às ${hora(iso)}`;
  return diaHora(iso);
}

export function CardValvula({ resumo }: { resumo: Resumo }) {
  const agora = useAgora(15_000);
  const { valvula, dispositivo } = resumo;
  const comando = useEnviarComando(dispositivo?.serial, resumo.cultivo.id);
  const [aberto, setAberto] = useState(false);
  const [min, setMin] = useState("10");

  const semContato = !dispositivo || dispositivo.status === "sem_contato";
  const motivoBloqueio = !dispositivo
    ? "Instale a placa neste cultivo para usar a válvula."
    : semContato
      ? "A placa está sem contato: o comando não chegaria a tempo."
      : null;

  const minutosValidos = Number(min) >= 1 && Number(min) <= 120 && Number.isFinite(Number(min));

  const enviar = (acao: "abrir" | "cancelar") =>
    comando.mutate(acao === "abrir" ? { acao, minutos: Number(min) } : { acao }, {
      onSuccess: () => {
        setAberto(false);
        toast.success(
          acao === "abrir"
            ? `Comando enviado: abrir por ${min} min. Aguardando a placa…`
            : "Comando enviado: fechar a válvula. Aguardando a placa…",
        );
      },
      onError: (e) => toast.error(mensagemDeErro(e)),
    });

  const andamento = valvula.em_andamento;
  const ultima = valvula.ultima;

  return (
    <Card className="h-full shadow-sm">
      <CardContent className="flex h-full flex-col gap-4">
        <Rotulo icone={Waves}>Válvula</Rotulo>

        {andamento ? (
          <div>
            <p className="flex items-center gap-2 font-display text-xl font-semibold text-irrigacao">
              <span className="relative flex size-2.5">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" />
                <span className="relative inline-flex size-2.5 rounded-full bg-current" />
              </span>
              Aberta há {duracao(new Date(andamento.ts_inicio * 1000), agora)}
            </p>
            <p className="text-sm text-muted-foreground">
              Irrigação {ORIGEM_IRRIGACAO[andamento.origem].toLowerCase()} desde{" "}
              {hora(andamento.ts_inicio)}
            </p>
          </div>
        ) : (
          <p className="font-display text-xl font-semibold">Fechada</p>
        )}

        <dl className="grid gap-2 text-sm">
          <div className="flex items-start gap-2">
            <CalendarClock className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <dt className="sr-only">Próxima irrigação</dt>
            <dd>
              {valvula.proxima_prevista
                ? `Próxima: ${quando(valvula.proxima_prevista, agora)}`
                : resumo.cultivo.irrigacao_automatica
                  ? "Sem irrigação automática prevista"
                  : "Irrigação automática desligada"}
            </dd>
          </div>
          <div className="flex items-start gap-2">
            <History className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <dt className="sr-only">Última irrigação</dt>
            <dd className="numeros">
              {ultima
                ? `Última: ${diaMes(ultima.ts_inicio)} · ${minutos(ultima.minutos)} · ${mm(ultima.mm)}`
                : "Nenhuma irrigação registrada"}
            </dd>
          </div>
        </dl>

        <div className="mt-auto flex flex-wrap gap-2">
          {andamento ? (
            <Button
              variant="outline"
              onClick={() => enviar("cancelar")}
              disabled={!!motivoBloqueio || comando.isPending}
            >
              {comando.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <PowerOff className="size-4" />
              )}
              Cancelar
            </Button>
          ) : (
            <Dialog open={aberto} onOpenChange={setAberto}>
              <Tooltip>
                <TooltipTrigger asChild>
                  {/* span: o tooltip precisa de um elemento que receba o mouse mesmo com o botão desabilitado */}
                  <span tabIndex={motivoBloqueio ? 0 : -1}>
                    <DialogTrigger asChild>
                      <Button disabled={!!motivoBloqueio}>
                        <Power className="size-4" />
                        Abrir manualmente
                      </Button>
                    </DialogTrigger>
                  </span>
                </TooltipTrigger>
                {motivoBloqueio && <TooltipContent>{motivoBloqueio}</TooltipContent>}
              </Tooltip>
              <DialogContent className="sm:max-w-sm">
                <DialogHeader>
                  <DialogTitle>Abrir a válvula</DialogTitle>
                  <DialogDescription>
                    A placa {dispositivo?.serial} abre a válvula e fecha sozinha depois do tempo
                    escolhido. O comando vale por 10 minutos.
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-2">
                  <Label htmlFor="minutos">Minutos (1 a 120)</Label>
                  <Input
                    id="minutos"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={120}
                    value={min}
                    onChange={(e) => setMin(e.target.value)}
                    aria-invalid={!minutosValidos}
                  />
                  {!minutosValidos && (
                    <p className="text-xs text-destructive">Informe de 1 a 120 minutos.</p>
                  )}
                </div>
                <DialogFooter>
                  <DialogClose asChild>
                    <Button variant="outline">Voltar</Button>
                  </DialogClose>
                  <Button
                    onClick={() => enviar("abrir")}
                    disabled={!minutosValidos || comando.isPending}
                  >
                    {comando.isPending && <Loader2 className="size-4 animate-spin" />}
                    Abrir por {minutosValidos ? min : "…"} min
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
