/** Avisos que podem chegar por dois caminhos (evento do SSE e mudança vista na tela). */

const mostrados = new Set<string>();

/** "Configuração vN aplicada": vem do evento do SSE ou da tela que viu a mudança. */
export function idToastConfig(instalacaoId: number, cfgV: number) {
  return `config-aplicada-${instalacaoId}-${cfgV}`;
}

/** Mostra o aviso só na primeira vez que o id aparece; o segundo caminho é ignorado. */
export function avisarUmaVez(id: string, mostrar: () => void) {
  if (mostrados.has(id)) return;
  mostrados.add(id);
  mostrar();
}
