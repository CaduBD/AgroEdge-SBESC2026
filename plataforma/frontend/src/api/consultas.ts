/** Hooks do TanStack Query para cada recurso da API. */
import {
  QueryCache,
  QueryClient,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, ErroApi, ErroRede } from "./cliente";
import { definirConexao } from "./conexao";
import type {
  BotCanal,
  CodigoVinculo,
  Comando,
  Cultivo,
  CultivoEntrada,
  Cultura,
  Diario,
  Dispositivo,
  DispositivoDetalhe,
  Fazenda,
  Instalacao,
  Irrigacao,
  Resumo,
  Serie,
  SituacaoCodigo,
  Usuario,
  VinculoCanal,
} from "./tipos";

export const chaves = {
  eu: ["eu"] as const,
  culturas: ["culturas"] as const,
  fazendas: ["fazendas"] as const,
  cultivos: (fazendaId: number) => ["fazendas", fazendaId, "cultivos"] as const,
  resumo: (cultivoId: number) => ["cultivos", cultivoId, "resumo"] as const,
  comandos: (serial: string) => ["dispositivos", serial, "comandos"] as const,
  leituras: (cultivoId: number, ...filtros: string[]) =>
    ["cultivos", cultivoId, "leituras", ...filtros] as const,
  diarios: (cultivoId: number, ...filtros: string[]) =>
    ["cultivos", cultivoId, "diarios", ...filtros] as const,
  irrigacoes: (cultivoId: number, ...filtros: string[]) =>
    ["cultivos", cultivoId, "irrigacoes", ...filtros] as const,
  botTelegram: ["canais", "telegram"] as const,
  vinculos: ["canais", "vinculos"] as const,
};

export function criarClienteQuery(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (erro) => {
        if (erro instanceof ErroRede) definirConexao(false);
      },
      onSuccess: () => definirConexao(true),
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        // Erros da API (401, 404…) não adiantam repetir; queda de rede sim, com espera crescente.
        retry: (falhas, erro) => erro instanceof ErroRede && falhas < 1000,
        retryDelay: (tentativa) => Math.min(1000 * 2 ** tentativa, 15_000),
      },
    },
  });
}

// ---------------------------------------------------------------- sessão

export function useEu() {
  return useQuery({
    queryKey: chaves.eu,
    queryFn: async () => {
      try {
        return await api<Usuario>("/auth/eu");
      } catch (e) {
        if (e instanceof ErroApi && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: Infinity,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dados: { email: string; senha: string }) =>
      api<Usuario>("/auth/login", "POST", dados),
    onSuccess: (usuario) => {
      qc.clear();
      qc.setQueryData(chaves.eu, usuario);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/auth/logout", "POST"),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(chaves.eu, null);
    },
  });
}

export function useTrocarSenha() {
  return useMutation({
    mutationFn: (dados: { senha_atual: string; senha_nova: string }) =>
      api("/auth/senha", "PATCH", dados),
  });
}

// ---------------------------------------------------------------- catálogo, fazendas, cultivos

export function useCulturas() {
  return useQuery({
    queryKey: chaves.culturas,
    queryFn: () => api<Cultura[]>("/culturas"),
    staleTime: Infinity,
  });
}

export function useFazendas() {
  return useQuery({ queryKey: chaves.fazendas, queryFn: () => api<Fazenda[]>("/fazendas") });
}

/** Todas as fazendas com seus cultivos ativos (para o seletor do topo). */
export function useFazendasComCultivos() {
  const fazendas = useFazendas();
  const lista = fazendas.data ?? [];
  const cultivos = useQueries({
    queries: lista.map((f) => ({
      queryKey: chaves.cultivos(f.id),
      queryFn: () => api<Cultivo[]>(`/fazendas/${f.id}/cultivos`),
    })),
  });
  const carregando = fazendas.isPending || cultivos.some((c) => c.isPending);
  const grupos = lista.map((fazenda, i) => ({ fazenda, cultivos: cultivos[i]?.data ?? [] }));
  return { grupos, carregando, erro: fazendas.error ?? cultivos.find((c) => c.error)?.error };
}

// ---------------------------------------------------------------- tela Início

export function useResumo(cultivoId: number | undefined) {
  return useQuery({
    queryKey: chaves.resumo(cultivoId ?? 0),
    queryFn: () => api<Resumo>(`/cultivos/${cultivoId}/resumo`),
    enabled: !!cultivoId,
    // Os eventos do SSE atualizam na hora. O intervalo cobre o que muda só com o tempo
    // (ex.: "ao vivo" → "atualizado há X" quando a placa para de mandar sem cair).
    refetchInterval: 60_000,
  });
}

// ---------------------------------------------------------------- válvula

export function useEnviarComando(serial: string | undefined, cultivoId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dados: { acao: "abrir" | "cancelar"; minutos?: number }) =>
      api<Comando>(`/dispositivos/${serial}/comandos`, "POST", dados),
    onSuccess: () => {
      if (serial) qc.invalidateQueries({ queryKey: chaves.comandos(serial) });
      qc.invalidateQueries({ queryKey: chaves.resumo(cultivoId) });
    },
  });
}

// ---------------------------------------------------------------- Histórico

export function useLeituras(cultivoId: number, de: string, ate: string, variaveis: string[]) {
  const vars = variaveis.join(",");
  return useQuery({
    queryKey: chaves.leituras(cultivoId, de, ate, vars),
    queryFn: () =>
      api<Serie>(
        `/cultivos/${cultivoId}/leituras?${new URLSearchParams({ de, ate, variaveis: vars })}`,
      ),
    enabled: variaveis.length > 0,
    placeholderData: (anterior) => anterior,
  });
}

export function useDiarios(cultivoId: number, de: string, ate: string) {
  return useQuery({
    queryKey: chaves.diarios(cultivoId, de, ate),
    queryFn: () =>
      api<Diario[]>(`/cultivos/${cultivoId}/diarios?${new URLSearchParams({ de, ate })}`),
    placeholderData: (anterior) => anterior,
  });
}

export function useIrrigacoes(cultivoId: number, de: string, ate: string) {
  return useQuery({
    queryKey: chaves.irrigacoes(cultivoId, de, ate),
    queryFn: () =>
      api<Irrigacao[]>(`/cultivos/${cultivoId}/irrigacoes?${new URLSearchParams({ de, ate })}`),
    placeholderData: (anterior) => anterior,
  });
}

// ---------------------------------------------------------------- fazendas e cultivos (edição)

/** Depois de mudar fazendas ou cultivos, tudo que depende deles é atualizado. */
function invalidarCadastro(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["fazendas"] });
  qc.invalidateQueries({ queryKey: ["cultivos"] });
  qc.invalidateQueries({ queryKey: ["dispositivos"] });
}

export function useSalvarFazenda() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...dados }: { id?: number; nome: string; municipio?: string | null }) =>
      id
        ? api<Fazenda>(`/fazendas/${id}`, "PATCH", dados)
        : api<Fazenda>("/fazendas", "POST", dados),
    onSuccess: () => invalidarCadastro(qc),
  });
}

export function useExcluirFazenda() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api(`/fazendas/${id}`, "DELETE"),
    onSuccess: () => invalidarCadastro(qc),
  });
}

export function useCultivosDaFazenda(fazendaId: number, arquivados: boolean) {
  return useQuery({
    queryKey: [...chaves.cultivos(fazendaId), { arquivados }],
    queryFn: () => api<Cultivo[]>(`/fazendas/${fazendaId}/cultivos?arquivados=${arquivados}`),
  });
}

export function useCultivo(id: number | undefined) {
  return useQuery({
    queryKey: ["cultivos", id ?? 0, "detalhe"],
    queryFn: () => api<Cultivo>(`/cultivos/${id}`),
    enabled: !!id,
  });
}

export function useSalvarCultivo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      fazendaId,
      dados,
    }: {
      id?: number;
      fazendaId: number;
      dados: Partial<CultivoEntrada>;
    }) =>
      id
        ? api<Cultivo>(`/cultivos/${id}`, "PATCH", dados)
        : api<Cultivo>(`/fazendas/${fazendaId}/cultivos`, "POST", dados),
    onSuccess: () => invalidarCadastro(qc),
  });
}

export function useNovaPoda() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: string }) =>
      api<Cultivo>(`/cultivos/${id}/poda`, "POST", { data }),
    onSuccess: () => invalidarCadastro(qc),
  });
}

export function useArquivarCultivo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<Cultivo>(`/cultivos/${id}/arquivar`, "POST"),
    onSuccess: () => invalidarCadastro(qc),
  });
}

// ---------------------------------------------------------------- dispositivos

export function useDispositivos() {
  return useQuery({
    queryKey: ["dispositivos"],
    queryFn: () => api<Dispositivo[]>("/dispositivos"),
  });
}

export function useDispositivo(serial: string | undefined) {
  return useQuery({
    queryKey: ["dispositivos", serial ?? "", "detalhe"],
    queryFn: () => api<DispositivoDetalhe>(`/dispositivos/${serial}`),
    enabled: !!serial,
    refetchInterval: 60_000,
  });
}

export function useInstalacoes(serial: string | undefined) {
  return useQuery({
    queryKey: ["dispositivos", serial ?? "", "instalacoes"],
    queryFn: () => api<Instalacao[]>(`/dispositivos/${serial}/instalacoes`),
    enabled: !!serial,
  });
}

export function useComandos(serial: string | undefined) {
  return useQuery({
    queryKey: chaves.comandos(serial ?? ""),
    queryFn: () => api<Comando[]>(`/dispositivos/${serial}/comandos`),
    enabled: !!serial,
  });
}

export function useInstalar(serial: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dados: { cultivo_id: number; inicio?: string }) =>
      api<Instalacao>(`/dispositivos/${serial}/instalar`, "POST", dados),
    onSuccess: () => invalidarCadastro(qc),
  });
}

// ---------------------------------------------------------------- chatbot (Conta → Telegram)

export function useBotTelegram() {
  return useQuery({
    queryKey: chaves.botTelegram,
    queryFn: () => api<BotCanal>("/canais/telegram"),
  });
}

export function useVinculos() {
  return useQuery({
    queryKey: chaves.vinculos,
    queryFn: () => api<VinculoCanal[]>("/canais/vinculos"),
  });
}

/** Enquanto o QR code está na tela: consulta a cada 2 s se a conversa já conectou. */
export function useSituacaoCodigo(codigo: string | undefined) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["canais", "codigos", codigo ?? ""],
    queryFn: async () => {
      const situacao = await api<SituacaoCodigo>(`/canais/codigos/${codigo}`);
      if (situacao.vinculo) await qc.invalidateQueries({ queryKey: chaves.vinculos });
      return situacao;
    },
    enabled: !!codigo,
    refetchInterval: (consulta) => (consulta.state.data?.vinculo ? false : 2_000),
  });
}

export function useGerarCodigoTelegram() {
  return useMutation({
    mutationFn: () => api<CodigoVinculo>("/canais/telegram/codigo", "POST"),
  });
}

export function useDesconectarConversa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api(`/canais/vinculos/${id}`, "DELETE"),
    onSuccess: () => qc.invalidateQueries({ queryKey: chaves.vinculos }),
  });
}
