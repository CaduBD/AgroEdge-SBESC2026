/** Cliente HTTP da API. Usa o cookie de sessão (mesma origem). */

export class ErroApi extends Error {
  readonly status: number;
  readonly codigo: string;

  constructor(status: number, codigo: string, mensagem: string) {
    super(mensagem);
    this.status = status;
    this.codigo = codigo;
  }
}

/** Falha de rede (servidor fora do ar): diferente de um erro respondido pela API. */
export class ErroRede extends Error {}

type Metodo = "GET" | "POST" | "PATCH" | "DELETE";

export async function api<T>(caminho: string, metodo: Metodo = "GET", corpo?: unknown): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(`/api${caminho}`, {
      method: metodo,
      credentials: "same-origin",
      headers: corpo !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
    });
  } catch {
    throw new ErroRede("Sem conexão com o servidor.");
  }
  if (resposta.status === 204) return undefined as T;
  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    if (resposta.status >= 502 && resposta.status <= 504 && !dados) {
      throw new ErroRede("Sem conexão com o servidor.");
    }
    throw new ErroApi(
      resposta.status,
      dados?.erro ?? "erro",
      dados?.mensagem ?? "Algo deu errado. Tente de novo.",
    );
  }
  return dados as T;
}

export function mensagemDeErro(erro: unknown): string {
  return erro instanceof Error ? erro.message : "Algo deu errado. Tente de novo.";
}
