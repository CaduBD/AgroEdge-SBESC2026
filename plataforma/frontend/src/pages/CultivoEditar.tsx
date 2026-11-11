import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, ArrowLeft, CalendarPlus, Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { z } from "zod";

import { ErroApi, mensagemDeErro } from "@/api/cliente";
import {
  useCultivo,
  useCulturas,
  useFazendas,
  useNovaPoda,
  useSalvarCultivo,
} from "@/api/consultas";
import type { Cultivo, CultivoEntrada } from "@/api/tipos";
import { EstadoConfiguracao } from "@/components/cultivos/EstadoConfiguracao";
import { NaoEncontrada } from "@/pages/NaoEncontrada";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { numero } from "@/lib/formatar";
import { hojeLocal } from "@/lib/periodo";
import { FONTE_IRRIGACAO, INICIO_USO, TEXTURA_SOLO } from "@/lib/rotulos";
import { aguaDisponivel, calcularTawRaw, TAW_TREINO } from "@/lib/solo";
import { cn } from "@/lib/utils";

const opcional = (schema: z.ZodType<number>) =>
  z.preprocess(
    (v) => (v === "" || v === null || Number.isNaN(v) ? undefined : v),
    schema.optional(),
  );

const esquema = z
  .object({
    fazenda_id: z.coerce.number().int().positive("Escolha a fazenda"),
    nome: z.string().trim().min(1, "Dê um nome ao cultivo").max(100),
    cultura: z.string().min(1, "Escolha a cultura"),
    data_referencia: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Informe a data"),
    textura_solo: z.enum(["arenoso", "franco_arenoso", "argiloso", "avancado"]),
    agua_disp: opcional(z.coerce.number().min(0.06, "Mínimo 0,06").max(0.18, "Máximo 0,18")),
    raiz_m: opcional(z.coerce.number().min(0.4, "Mínimo 0,4 m").max(0.8, "Máximo 0,8 m")),
    eficiencia: z.coerce.number().min(0.5, "Mínimo 0,5").max(0.95, "Máximo 0,95"),
    area_m2: z.coerce.number().positive("Deve ser maior que zero"),
    vazao_l_h: z.coerce.number().positive("Deve ser maior que zero"),
    n_plantas: opcional(z.coerce.number().int("Número inteiro").positive("Deve ser positivo")),
    fonte_irrigacao: z.enum(["sensor", "manual", "tempo", "parcial", "nenhuma"]),
    inicio_uso: z.enum(["ciclo", "apos_irr", "meio"]),
    irrigacao_automatica: z.boolean(),
    hora_irrigacao: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Use HH:MM"),
  })
  .refine((d) => d.textura_solo !== "avancado" || d.agua_disp != null, {
    path: ["agua_disp"],
    message: "Informe a água disponível",
  });

type Dados = z.infer<typeof esquema>;

function padrao(fazendaId: number | undefined): Partial<Dados> {
  return {
    fazenda_id: fazendaId,
    nome: "",
    cultura: "",
    data_referencia: hojeLocal(),
    textura_solo: "franco_arenoso",
    eficiencia: 0.9,
    fonte_irrigacao: "tempo",
    inicio_uso: "meio",
    irrigacao_automatica: true,
    hora_irrigacao: "05:00",
  };
}

function dosDados(c: Cultivo): Partial<Dados> {
  return {
    fazenda_id: c.fazenda_id,
    nome: c.nome,
    cultura: c.cultura,
    data_referencia: c.data_referencia,
    textura_solo: c.textura_solo,
    agua_disp: c.textura_solo === "avancado" ? c.agua_disp : undefined,
    raiz_m: c.raiz_m ?? undefined,
    eficiencia: c.eficiencia,
    area_m2: c.area_m2,
    vazao_l_h: c.vazao_l_h,
    n_plantas: c.n_plantas ?? undefined,
    fonte_irrigacao: c.fonte_irrigacao,
    inicio_uso: c.inicio_uso,
    irrigacao_automatica: c.irrigacao_automatica,
    hora_irrigacao: c.hora_irrigacao,
  };
}

function Campo({
  id,
  rotulo,
  erro,
  ajuda,
  children,
  className,
}: {
  id: string;
  rotulo: string;
  erro?: string;
  ajuda?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid content-start gap-2", className)}>
      <Label htmlFor={id}>{rotulo}</Label>
      {children}
      {erro ? (
        <p className="text-xs text-destructive">{erro}</p>
      ) : ajuda ? (
        <p className="text-xs text-muted-foreground">{ajuda}</p>
      ) : null}
    </div>
  );
}

function DialogoPoda({
  cultivo,
  referencia,
}: {
  cultivo: Cultivo;
  referencia: "poda" | "floracao";
}) {
  const [aberto, setAberto] = useState(false);
  const [data, setData] = useState(hojeLocal());
  const poda = useNovaPoda();
  const nome = referencia === "poda" ? "poda" : "floração";
  return (
    <Dialog open={aberto} onOpenChange={setAberto}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          <CalendarPlus className="size-4" /> Registrar nova {nome}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Registrar nova {nome}</DialogTitle>
          <DialogDescription>
            Começa um novo ciclo a partir desta data.
            {cultivo.configuracao && " A nova data é enviada à placa."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="data-poda">Data da {nome}</Label>
          <Input
            id="data-poda"
            type="date"
            value={data}
            max={hojeLocal()}
            onChange={(e) => setData(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setAberto(false)}>
            Voltar
          </Button>
          <Button
            type="button"
            disabled={!data || poda.isPending}
            onClick={() =>
              poda.mutate(
                { id: cultivo.id, data },
                {
                  onSuccess: () => {
                    toast.success(`Nova ${nome} registrada.`);
                    setAberto(false);
                  },
                  onError: (e) => toast.error(mensagemDeErro(e)),
                },
              )
            }
          >
            {poda.isPending && <Loader2 className="size-4 animate-spin" />}
            Registrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Formulário de cultivo (seção 12.5), em seções. Serve para criar e editar. */
export function CultivoEditar() {
  const { cultivoId } = useParams();
  const [params] = useSearchParams();
  const id = cultivoId ? Number(cultivoId) : undefined;
  const navegar = useNavigate();

  const cultivo = useCultivo(id);
  const culturas = useCulturas();
  const fazendas = useFazendas();
  const salvar = useSalvarCultivo();

  const fazendaInicial = Number(params.get("fazenda")) || fazendas.data?.[0]?.id;
  const {
    register,
    control,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isDirty },
  } = useForm<Dados>({
    resolver: zodResolver(esquema) as never,
    defaultValues: padrao(fazendaInicial),
  });

  // Ao carregar o cultivo (edição) ou as fazendas (criação), preenche o formulário.
  useEffect(() => {
    if (cultivo.data) reset(dosDados(cultivo.data));
  }, [cultivo.data, reset]);
  useEffect(() => {
    if (!id && fazendaInicial) setValue("fazenda_id", fazendaInicial);
  }, [id, fazendaInicial, setValue]);

  const [textura, chaveCultura, aguaDigitada, raizDigitada] = useWatch({
    control,
    name: ["textura_solo", "cultura", "agua_disp", "raiz_m"],
  });
  const cultura = culturas.data?.find((c) => c.chave === chaveCultura);
  const raiz =
    textura === "avancado" && raizDigitada ? Number(raizDigitada) : (cultura?.raiz_m ?? 0.6);
  const solo = calcularTawRaw(
    aguaDisponivel(textura, aguaDigitada ? Number(aguaDigitada) : null),
    raiz,
    cultura?.p ?? 0.5,
  );

  if (id && cultivo.error instanceof ErroApi && cultivo.error.status === 404)
    return <NaoEncontrada />;
  if ((id && cultivo.isPending) || culturas.isPending || fazendas.isPending) {
    return <Skeleton className="h-96 rounded-xl" />;
  }

  const comPlaca = !!cultivo.data?.configuracao;

  const enviar = (d: Dados) => {
    const { fazenda_id, ...resto } = d;
    const dados: Partial<CultivoEntrada> = {
      ...resto,
      agua_disp: d.textura_solo === "avancado" ? d.agua_disp : null,
      raiz_m: d.textura_solo === "avancado" ? (d.raiz_m ?? null) : null,
      n_plantas: d.n_plantas ?? null,
    };
    salvar.mutate(
      { id, fazendaId: fazenda_id, dados },
      {
        onSuccess: (salvo) => {
          if (!id) {
            toast.success("Cultivo cadastrado.");
            navegar(`/cultivos/${salvo.id}/editar`, { replace: true });
          } else {
            toast.success(
              salvo.configuracao && !salvo.configuracao.aplicada
                ? `Salvo. Configuração v${salvo.configuracao.cfg_v} enviada à placa.`
                : "Salvo.",
            );
            reset(dosDados(salvo));
          }
        },
        onError: (e) => toast.error(mensagemDeErro(e)),
      },
    );
  };

  const referencia = cultura?.referencia ?? "poda";
  const nomeReferencia = referencia === "poda" ? "poda" : "início da floração";

  return (
    <form onSubmit={handleSubmit(enviar)} className="grid max-w-3xl gap-5" noValidate>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="ghost" size="icon" asChild aria-label="Voltar">
          <Link to="/cultivos">
            <ArrowLeft className="size-4" />
          </Link>
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-semibold">
            {id ? (cultivo.data?.nome ?? "Cultivo") : "Novo cultivo"}
          </h1>
          {id && <EstadoConfiguracao configuracao={cultivo.data?.configuracao} />}
        </div>
      </div>

      {/* Identificação */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Identificação</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Campo id="nome" rotulo="Nome do cultivo" erro={errors.nome?.message}>
            <Input id="nome" placeholder="Ex.: Pomar 2 · Tommy" {...register("nome")} />
          </Campo>
          <Campo id="fazenda" rotulo="Fazenda" erro={errors.fazenda_id?.message}>
            <Controller
              control={control}
              name="fazenda_id"
              render={({ field }) => (
                <Select
                  value={field.value ? String(field.value) : ""}
                  onValueChange={(v) => field.onChange(Number(v))}
                  disabled={!!id}
                >
                  <SelectTrigger id="fazenda" className="w-full">
                    <SelectValue placeholder="Escolha a fazenda" />
                  </SelectTrigger>
                  <SelectContent>
                    {fazendas.data?.map((f) => (
                      <SelectItem key={f.id} value={String(f.id)}>
                        {f.nome}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Campo>
        </CardContent>
      </Card>

      {/* Cultura e ciclo */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Cultura e ciclo</CardTitle>
          <CardDescription>
            O dia do ciclo é contado a partir da {cultura ? nomeReferencia : "poda ou da floração"}.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Campo
            id="cultura"
            rotulo="Cultura"
            erro={errors.cultura?.message}
            ajuda={cultura && `Ciclo de ${cultura.ciclo_dias} dias, contado da ${nomeReferencia}.`}
          >
            <Controller
              control={control}
              name="cultura"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="cultura" className="w-full">
                    <SelectValue placeholder="Escolha a cultura" />
                  </SelectTrigger>
                  <SelectContent>
                    {culturas.data?.map((c) => (
                      <SelectItem key={c.chave} value={c.chave}>
                        {c.nome}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Campo>
          <Campo
            id="data_referencia"
            rotulo={`Data da ${cultura ? nomeReferencia : "referência"}`}
            erro={errors.data_referencia?.message}
          >
            <Input
              id="data_referencia"
              type="date"
              max={hojeLocal()}
              {...register("data_referencia")}
            />
          </Campo>
          {id && cultivo.data && (
            <div className="sm:col-span-2">
              <DialogoPoda cultivo={cultivo.data} referencia={referencia} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Solo */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Solo</CardTitle>
          <CardDescription>Na dúvida, use Franco-arenoso (padrão do modelo).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <Controller
            control={control}
            name="textura_solo"
            render={({ field }) => (
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Textura do solo">
                {(["arenoso", "franco_arenoso", "argiloso", "avancado"] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="radio"
                    aria-checked={field.value === t}
                    onClick={() => field.onChange(t)}
                    className={cn(
                      "inline-flex h-9 items-center rounded-full border px-4 text-sm font-medium transition-colors",
                      field.value === t
                        ? "border-primary bg-primary text-primary-foreground"
                        : "bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {TEXTURA_SOLO[t]}
                  </button>
                ))}
              </div>
            )}
          />
          {textura === "avancado" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo
                id="agua_disp"
                rotulo="Água disponível (m³/m³)"
                erro={errors.agua_disp?.message}
                ajuda="Da análise de solo: entre 0,06 e 0,18."
              >
                <Input
                  id="agua_disp"
                  type="number"
                  step="0.01"
                  inputMode="decimal"
                  {...register("agua_disp")}
                />
              </Campo>
              <Campo
                id="raiz_m"
                rotulo="Profundidade da raiz (m)"
                erro={errors.raiz_m?.message}
                ajuda={`Entre 0,4 e 0,8. Vazio = padrão da cultura (${numero(cultura?.raiz_m ?? 0.6)} m).`}
              >
                <Input
                  id="raiz_m"
                  type="number"
                  step="0.05"
                  inputMode="decimal"
                  {...register("raiz_m")}
                />
              </Campo>
            </div>
          )}
          <div className="grid gap-1 rounded-lg bg-muted/60 px-4 py-3 text-sm">
            <p className="numeros">
              <strong>TAW {numero(solo.taw, 0)} mm</strong> · raiz {numero(raiz)} m ·{" "}
              <strong>RAW {numero(solo.raw, 0)} mm</strong>
            </p>
            <p className="text-xs text-muted-foreground">
              Água total disponível na zona da raiz e a parte que a planta usa sem estresse.
            </p>
            {solo.foraDaFaixa && (
              <p className="mt-1 flex items-start gap-1.5 text-xs font-medium text-estado-moderado">
                <AlertTriangle className="mt-px size-3.5 shrink-0" />
                TAW fora da faixa de treino do classificador ({TAW_TREINO[0]} a {TAW_TREINO[1]} mm):
                a classe pode ser pouco confiável.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Irrigação */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Irrigação</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Campo id="area_m2" rotulo="Área por planta (m²)" erro={errors.area_m2?.message}>
            <Input
              id="area_m2"
              type="number"
              step="0.1"
              inputMode="decimal"
              {...register("area_m2")}
            />
          </Campo>
          <Campo
            id="vazao_l_h"
            rotulo="Vazão por planta (L/h)"
            erro={errors.vazao_l_h?.message}
            ajuda="Soma dos emissores de uma planta."
          >
            <Input
              id="vazao_l_h"
              type="number"
              step="0.1"
              inputMode="decimal"
              {...register("vazao_l_h")}
            />
          </Campo>
          <Campo
            id="eficiencia"
            rotulo="Eficiência da irrigação"
            erro={errors.eficiencia?.message}
            ajuda="Gotejamento ≈ 0,90; microaspersão ≈ 0,85."
          >
            <Input
              id="eficiencia"
              type="number"
              step="0.01"
              inputMode="decimal"
              {...register("eficiencia")}
            />
          </Campo>
          <Campo
            id="n_plantas"
            rotulo="Nº de plantas (opcional)"
            erro={errors.n_plantas?.message}
            ajuda="Para mostrar os litros do cultivo inteiro."
          >
            <Input
              id="n_plantas"
              type="number"
              step="1"
              inputMode="numeric"
              {...register("n_plantas")}
            />
          </Campo>
          <div className="flex items-center justify-between gap-3 rounded-lg border px-4 py-3 sm:col-span-2">
            <div>
              <Label htmlFor="irrigacao_automatica">Irrigação automática</Label>
              <p className="text-xs text-muted-foreground">
                A placa abre a válvula sozinha no horário.
              </p>
            </div>
            <Controller
              control={control}
              name="irrigacao_automatica"
              render={({ field }) => (
                <Switch
                  id="irrigacao_automatica"
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
              )}
            />
          </div>
          <Campo
            id="hora_irrigacao"
            rotulo="Hora da irrigação"
            erro={errors.hora_irrigacao?.message}
          >
            <Input id="hora_irrigacao" type="time" step="60" {...register("hora_irrigacao")} />
          </Campo>
          <Campo id="fonte_irrigacao" rotulo="Fonte da informação de irrigação">
            <Controller
              control={control}
              name="fonte_irrigacao"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="fonte_irrigacao" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(FONTE_IRRIGACAO).map(([k, v]) => (
                      <SelectItem key={k} value={k}>
                        {v}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Campo>
          <Campo id="inicio_uso" rotulo="Início do uso da placa" className="sm:col-span-2">
            <Controller
              control={control}
              name="inicio_uso"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="inicio_uso" className="w-full sm:w-1/2">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(INICIO_USO).map(([k, v]) => (
                      <SelectItem key={k} value={k}>
                        {v}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </Campo>
        </CardContent>
      </Card>

      {cultivo.data?.avisos.map((a) => (
        <Alert key={a}>
          <AlertTriangle className="size-4" />
          <AlertDescription>{a}</AlertDescription>
        </Alert>
      ))}

      {/* Rodapé fixo */}
      <div className="sticky bottom-0 z-20 -mx-3 border-t bg-background/90 backdrop-blur sm:-mx-6 lg:mx-0 lg:rounded-xl lg:border">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <span className="text-sm">
            {id ? (
              isDirty ? (
                <span className="text-muted-foreground">Alterações não salvas</span>
              ) : (
                <EstadoConfiguracao configuracao={cultivo.data?.configuracao} />
              )
            ) : null}
          </span>
          <Button type="submit" disabled={salvar.isPending || (!!id && !isDirty)}>
            {salvar.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            {comPlaca ? "Salvar e enviar à placa" : "Salvar"}
          </Button>
        </div>
      </div>
    </form>
  );
}
