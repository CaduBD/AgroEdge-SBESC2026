import { Loader2, Save, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { mensagemDeErro } from "@/api/cliente";
import { useEditarDispositivo } from "@/api/consultas";
import type { DispositivoDetalhe } from "@/api/tipos";
import { EstadoConfiguracao } from "@/components/cultivos/EstadoConfiguracao";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const INTERVALOS = [1, 5, 10, 15, 30, 60];

/** Apelido e intervalo de telemetria. O intervalo vai na config: a placa confirma. */
export function CardConfigPlaca({ dispositivo: d }: { dispositivo: DispositivoDetalhe }) {
  const editar = useEditarDispositivo(d.serial);
  const [apelido, setApelido] = useState(d.apelido ?? "");
  const [intervalo, setIntervalo] = useState(String(d.intervalo_telemetria_min));

  useEffect(() => {
    setApelido(d.apelido ?? "");
    setIntervalo(String(d.intervalo_telemetria_min));
  }, [d.apelido, d.intervalo_telemetria_min]);

  const mudou =
    apelido.trim() !== (d.apelido ?? "") || Number(intervalo) !== d.intervalo_telemetria_min;
  const inst = d.instalacao;
  const opcoes = INTERVALOS.includes(d.intervalo_telemetria_min)
    ? INTERVALOS
    : [...INTERVALOS, d.intervalo_telemetria_min].sort((a, b) => a - b);

  const salvar = () =>
    editar.mutate(
      { apelido: apelido.trim() || null, intervalo_telemetria_min: Number(intervalo) },
      {
        onSuccess: (novo) => {
          const enviada = novo.instalacao && novo.instalacao.cfg_v !== inst?.cfg_v;
          toast.success(
            enviada ? `Salvo. Configuração v${novo.instalacao!.cfg_v} enviada à placa.` : "Salvo.",
          );
        },
        onError: (e) => toast.error(mensagemDeErro(e)),
      },
    );

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings2 className="size-4" /> Configuração da placa
        </CardTitle>
        <CardDescription>
          No campo, 15 min é o padrão: leituras mais frequentes gastam mais bateria e dados.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <div className="grid gap-2">
          <Label htmlFor="apelido">Apelido</Label>
          <Input
            id="apelido"
            value={apelido}
            maxLength={60}
            placeholder="Ex.: Placa do pomar 2"
            onChange={(e) => setApelido(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="intervalo">Intervalo de telemetria</Label>
          <Select value={intervalo} onValueChange={setIntervalo}>
            <SelectTrigger id="intervalo" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {opcoes.map((m) => (
                <SelectItem key={m} value={String(m)}>
                  {m === 1 ? "1 minuto" : `${m} minutos`}
                  {m === 15 && " (padrão)"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={salvar} disabled={!mudou || editar.isPending}>
          {editar.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Save className="size-4" />
          )}
          {inst ? "Salvar e enviar à placa" : "Salvar"}
        </Button>
        {inst && (
          <div className="sm:col-span-3">
            <EstadoConfiguracao
              configuracao={{
                serial: d.serial,
                instalacao_id: inst.id,
                cfg_v: inst.cfg_v,
                cfg_v_aplicada: inst.cfg_v_aplicada,
                aplicada: inst.cfg_v_aplicada === inst.cfg_v,
              }}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
