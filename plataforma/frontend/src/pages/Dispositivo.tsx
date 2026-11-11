import type { ColumnDef } from "@tanstack/react-table";
import {
  BatteryMedium,
  Check,
  ChevronDown,
  Copy,
  Cpu,
  Database,
  History,
  Link2,
  Plug,
  Settings2,
  ShieldAlert,
  Signal,
  Terminal,
} from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useComandos, useDispositivo, useDispositivos, useInstalacoes } from "@/api/consultas";
import type { Comando, Instalacao } from "@/api/tipos";
import { DialogoInstalar } from "@/components/dispositivo/DialogoInstalar";
import { EstadoVazio } from "@/components/EstadoVazio";
import { type MetaColuna, TabelaPaginada } from "@/components/historico/TabelaPaginada";
import { Rotulo } from "@/components/inicio/Cards";
import { PillStatus } from "@/components/PillStatus";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgora } from "@/hooks/useAgora";
import { diaHora, ha, numero } from "@/lib/formatar";
import { ESTADO_COMANDO, RESULTADO_COMANDO } from "@/lib/rotulos";
import { cn } from "@/lib/utils";

const ESTILO_COMANDO: Record<Comando["estado"], string> = {
  enviado: "text-sincronizando",
  executado: "text-estado-adequado",
  recusado: "text-estado-critico",
  expirado: "text-muted-foreground",
};

const colunasComandos: ColumnDef<Comando, unknown>[] = [
  { id: "quando", header: "Enviado", cell: ({ row }) => diaHora(row.original.criado_em) },
  {
    id: "acao",
    header: "Ação",
    cell: ({ row }) =>
      row.original.acao === "abrir"
        ? `Abrir por ${numero(row.original.minutos, 0)} min`
        : "Fechar a válvula",
  },
  {
    id: "estado",
    header: "Estado",
    cell: ({ row }) => (
      <span className={cn("font-medium", ESTILO_COMANDO[row.original.estado])}>
        {ESTADO_COMANDO[row.original.estado]}
      </span>
    ),
  },
  {
    id: "resultado",
    header: "Resposta da placa",
    cell: ({ row }) =>
      row.original.resultado
        ? `${RESULTADO_COMANDO[row.original.resultado] ?? row.original.resultado} · ${diaHora(row.original.respondido_em)}`
        : row.original.estado === "expirado"
          ? "Sem resposta em 10 min"
          : "—",
  },
];

const colunasInstalacoes: ColumnDef<Instalacao, unknown>[] = [
  {
    id: "cultivo",
    header: "Cultivo",
    cell: ({ row }) => (
      <Link
        className="font-medium hover:underline"
        to={`/cultivos/${row.original.cultivo_id}/inicio`}
      >
        {row.original.cultivo_nome}
      </Link>
    ),
  },
  { id: "inicio", header: "Desde", cell: ({ row }) => diaHora(row.original.inicio) },
  {
    id: "fim",
    header: "Até",
    cell: ({ row }) =>
      row.original.fim ? (
        diaHora(row.original.fim)
      ) : (
        <span className="font-medium text-estado-adequado">Atual</span>
      ),
  },
  {
    id: "cfg",
    header: "Configuração",
    meta: { numero: true } satisfies MetaColuna,
    cell: ({ row }) =>
      `v${row.original.cfg_v}${row.original.cfg_v_aplicada === row.original.cfg_v ? " aplicada" : ` (placa: v${row.original.cfg_v_aplicada ?? "—"})`}`,
  },
];

function Item({
  icone: Icone,
  rotulo,
  valor,
}: {
  icone: typeof Cpu;
  rotulo: string;
  valor: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
        <Icone className="size-4" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{rotulo}</p>
        <p className="numeros truncate font-semibold">{valor}</p>
      </div>
    </div>
  );
}

function BlocoCopiar({ texto }: { texto: string }) {
  const [copiado, setCopiado] = useState(false);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("Não foi possível copiar. Selecione o texto e copie à mão.");
    }
  };
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-lg border bg-muted/60 p-4 pr-12 font-mono text-sm leading-relaxed">
        {texto}
      </pre>
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 size-8"
        onClick={copiar}
        aria-label="Copiar"
      >
        {copiado ? <Check className="size-4 text-estado-adequado" /> : <Copy className="size-4" />}
      </Button>
    </div>
  );
}

/** Tela Dispositivo (seção 12.5). */
export function Dispositivo() {
  const agora = useAgora();
  const [params, setParams] = useSearchParams();
  const lista = useDispositivos();
  const serial = params.get("serial") ?? lista.data?.[0]?.serial;
  const disp = useDispositivo(serial);
  const instalacoes = useInstalacoes(serial);
  const comandos = useComandos(serial);
  const [verRejeitadas, setVerRejeitadas] = useState(false);

  if (lista.isPending || (serial && disp.isPending)) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-40 rounded-xl" />
        <Skeleton className="h-32 rounded-xl" />
      </div>
    );
  }
  if (!serial || !disp.data) {
    return (
      <EstadoVazio
        icone={Cpu}
        titulo="Nenhuma placa cadastrada"
        texto="Cadastre a placa no notebook com: make dispositivo SERIAL=agroedge-00001"
      />
    );
  }

  const d = disp.data;
  const inst = d.instalacao;
  const configLocal = [
    `MQTT_HOST = "${d.conexao.mqtt_host}"`,
    `MQTT_PORTA = ${d.conexao.mqtt_porta}`,
    `MQTT_USUARIO = "${d.conexao.mqtt_usuario}"`,
    `MQTT_SENHA = "…"  # gerada no cadastro da placa`,
  ].join("\n");

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Dispositivo</h1>
        {(lista.data?.length ?? 0) > 1 && (
          <Select value={serial} onValueChange={(s) => setParams({ serial: s }, { replace: true })}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {lista.data?.map((x) => (
                <SelectItem key={x.serial} value={x.serial}>
                  {x.serial}
                  {x.apelido && <span className="text-muted-foreground"> · {x.apelido}</span>}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* Aparelho */}
      <Card className="shadow-sm">
        <CardContent className="grid gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="grid size-11 place-items-center rounded-xl bg-accent text-primary">
                <Cpu className="size-5" />
              </div>
              <div>
                <p className="font-display text-xl font-semibold">{d.serial}</p>
                <p className="text-sm text-muted-foreground">{d.apelido ?? "BitDogLab"}</p>
              </div>
            </div>
            <PillStatus dispositivo={d} />
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-4">
            <Item
              icone={Signal}
              rotulo="Último contato"
              valor={d.ultimo_contato ? ha(d.ultimo_contato, agora) : "nunca"}
            />
            <Item
              icone={BatteryMedium}
              rotulo="Bateria"
              valor={
                d.bat_v != null ? `${numero(d.bat_v, 2)} V` : d.ultima_telemetria ? "na USB" : "—"
              }
            />
            <Item
              icone={Signal}
              rotulo="Sinal Wi-Fi"
              valor={d.rssi != null ? `${d.rssi} dBm` : "—"}
            />
            <Item icone={Database} rotulo="Leituras no buffer" valor={numero(d.buf ?? 0, 0)} />
            <Item
              icone={Settings2}
              rotulo="Configuração aplicada"
              valor={inst ? `v${inst.cfg_v_aplicada ?? "—"} de v${inst.cfg_v}` : "—"}
            />
          </div>
          {d.leituras_sem_cultivo > 0 && (
            <p className="text-sm text-estado-moderado">
              {numero(d.leituras_sem_cultivo, 0)} leituras sem cultivo (chegaram quando a placa não
              estava instalada em nenhum).
            </p>
          )}
        </CardContent>
      </Card>

      {/* Instalação atual */}
      <Card className="shadow-sm">
        <CardHeader className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Instalação atual</CardTitle>
            <CardDescription>
              {inst ? (
                <>
                  Em{" "}
                  <Link
                    className="font-medium text-foreground hover:underline"
                    to={`/cultivos/${inst.cultivo_id}/inicio`}
                  >
                    {inst.cultivo_nome}
                  </Link>{" "}
                  desde {diaHora(inst.inicio)}
                </>
              ) : (
                "A placa não está instalada em nenhum cultivo."
              )}
            </CardDescription>
          </div>
          <DialogoInstalar serial={d.serial} cultivoAtual={inst?.cultivo_id ?? null} />
        </CardHeader>
      </Card>

      {/* Comandos e histórico */}
      <div className="grid gap-3">
        <Rotulo icone={Terminal}>Comandos recentes</Rotulo>
        <TabelaPaginada
          dados={comandos.data ?? []}
          colunas={colunasComandos}
          porPagina={8}
          vazio="Nenhum comando enviado ainda. A válvula é aberta pela tela Início."
        />
      </div>
      <div className="grid gap-3">
        <Rotulo icone={History}>Histórico de instalações</Rotulo>
        <TabelaPaginada dados={instalacoes.data ?? []} colunas={colunasInstalacoes} porPagina={8} />
      </div>

      {/* Diagnóstico */}
      <Card className="gap-3 shadow-sm">
        <CardHeader>
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 text-left"
            onClick={() => setVerRejeitadas((v) => !v)}
            aria-expanded={verRejeitadas}
          >
            <span className="flex items-center gap-2 font-semibold">
              <ShieldAlert className="size-4 text-muted-foreground" />
              Mensagens rejeitadas ({d.rejeitadas.length})
            </span>
            <ChevronDown
              className={cn("size-4 transition-transform", verRejeitadas && "rotate-180")}
            />
          </button>
        </CardHeader>
        {verRejeitadas && (
          <CardContent className="grid gap-2">
            {d.rejeitadas.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nenhuma mensagem rejeitada desta placa.
              </p>
            ) : (
              d.rejeitadas.map((m) => (
                <div key={m.id} className="grid gap-1 rounded-lg border p-3 text-sm">
                  <div className="flex flex-wrap justify-between gap-2">
                    <span className="font-medium">{m.motivo}</span>
                    <span className="text-xs text-muted-foreground">{diaHora(m.recebido_em)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{m.topico}</p>
                  <code className="block truncate font-mono text-xs">{m.payload}</code>
                </div>
              ))
            )}
          </CardContent>
        )}
      </Card>

      {/* Como conectar */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Plug className="size-4" /> Como conectar a placa
          </CardTitle>
          <CardDescription>
            Notebook e placa no mesmo hotspot (2,4 GHz). Copie para o <code>config_local.py</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <BlocoCopiar texto={configLocal} />
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <Link2 className="mt-px size-3.5 shrink-0" />A senha MQTT não fica guardada no servidor:
            ela aparece uma vez, ao cadastrar a placa (make dispositivo). Para trocar, cadastre de
            novo com o mesmo serial.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
