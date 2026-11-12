import {
  CircleCheck,
  ExternalLink,
  Loader2,
  QrCode,
  RefreshCw,
  Send,
  Smartphone,
  TriangleAlert,
  Unlink,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { mensagemDeErro } from "@/api/cliente";
import {
  useBotTelegram,
  useDesconectarConversa,
  useGerarCodigoTelegram,
  useSituacaoCodigo,
  useVinculos,
} from "@/api/consultas";
import type { VinculoCanal } from "@/api/tipos";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgora } from "@/hooks/useAgora";
import { diaMes, ha } from "@/lib/formatar";

/** Conta → Telegram: conversas conectadas e o QR code para conectar uma nova. */
export function CardTelegram() {
  const [aberto, setAberto] = useState(false);
  const bot = useBotTelegram();
  const vinculos = useVinculos();
  const usuarioBot = bot.data?.usuario_bot;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="size-5 text-sky-500" aria-hidden />
          Telegram
        </CardTitle>
        <CardDescription>
          Receba os alertas da lavoura e controle a válvula por uma conversa no Telegram.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {bot.isPending || vinculos.isPending ? (
          <Skeleton className="h-16" />
        ) : (
          <>
            {!usuarioBot && (
              <div className="flex gap-3 rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                <p>
                  O chatbot ainda não está ligado. Inicie o bot (pasta <code>chatbot</code>,{" "}
                  <code>.\tarefas.ps1 bot</code>) para gerar o QR code.
                </p>
              </div>
            )}
            {vinculos.data && vinculos.data.length > 0 ? (
              <ul className="grid gap-2">
                {vinculos.data.map((v) => (
                  <LinhaVinculo key={v.id} vinculo={v} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nenhuma conversa conectada ainda.</p>
            )}
            <Button
              className="w-fit"
              onClick={() => setAberto(true)}
              disabled={!usuarioBot}
              aria-haspopup="dialog"
            >
              <QrCode className="size-4" aria-hidden />
              Conectar Telegram
            </Button>
          </>
        )}
      </CardContent>
      {aberto && <DialogoConectar aoFechar={() => setAberto(false)} />}
    </Card>
  );
}

function LinhaVinculo({ vinculo }: { vinculo: VinculoCanal }) {
  const [confirmar, setConfirmar] = useState(false);
  const desconectar = useDesconectarConversa();
  const nome = vinculo.nome ?? "Conversa do Telegram";
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-lg border p-3">
      <div className="flex size-9 items-center justify-center rounded-full bg-sky-500/10 text-sky-600 dark:text-sky-400">
        <Send className="size-4" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{nome}</p>
        <p className="text-xs text-muted-foreground">
          Conectada em {diaMes(vinculo.criado_em)}
          {vinculo.ultimo_uso && ` · último uso ${ha(vinculo.ultimo_uso)}`}
        </p>
      </div>
      <Badge variant={vinculo.alertas ? "secondary" : "outline"}>
        {vinculo.alertas ? "Alertas ligados" : "Alertas desligados"}
      </Badge>
      <Button variant="ghost" size="sm" onClick={() => setConfirmar(true)}>
        <Unlink className="size-4" aria-hidden />
        Desconectar
      </Button>
      <AlertDialog open={confirmar} onOpenChange={setConfirmar}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desconectar “{nome}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Essa conversa para de receber alertas e não consegue mais ver os dados nem abrir a
              válvula. Para voltar, é só gerar um novo QR code.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Voltar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                desconectar.mutate(vinculo.id, {
                  onSuccess: () => toast.success("Conversa desconectada."),
                  onError: (e) => toast.error(mensagemDeErro(e)),
                })
              }
            >
              Desconectar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </li>
  );
}

function DialogoConectar({ aoFechar }: { aoFechar: () => void }) {
  const gerar = useGerarCodigoTelegram();
  const codigo = gerar.data;
  const situacao = useSituacaoCodigo(codigo?.codigo);
  const agora = useAgora(1_000);
  const gerarCodigo = gerar.mutate;

  useEffect(() => {
    gerarCodigo();
  }, [gerarCodigo]);

  const novo = situacao.data?.vinculo;
  useEffect(() => {
    if (novo) toast.success("Telegram conectado.");
  }, [novo]);

  const restanteS = codigo
    ? Math.max(0, Math.round((new Date(codigo.expira_em).getTime() - agora.getTime()) / 1000))
    : 0;
  const vencido = !!codigo && restanteS === 0;

  return (
    <Dialog open onOpenChange={(abrir) => !abrir && aoFechar()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Conectar o Telegram</DialogTitle>
          <DialogDescription>
            Aponte a câmera do celular para o QR code. O Telegram abre a conversa com o bot já
            conectada à sua conta.
          </DialogDescription>
        </DialogHeader>

        {novo ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <CircleCheck className="size-12 text-estado-adequado" aria-hidden />
            <p className="text-lg font-semibold">Pronto, conectado!</p>
            <p className="text-sm text-muted-foreground">
              {novo.nome ?? "A conversa"} já recebe os alertas e pode usar o bot.
            </p>
          </div>
        ) : gerar.isError ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <TriangleAlert className="size-10 text-destructive" aria-hidden />
            <p className="text-sm">{mensagemDeErro(gerar.error)}</p>
          </div>
        ) : !codigo ? (
          <div className="flex justify-center py-10">
            <Loader2
              className="size-8 animate-spin text-muted-foreground"
              aria-label="Gerando QR code"
            />
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <div
              className={
                "rounded-xl bg-white p-3 shadow-sm transition-opacity" +
                (vencido ? " opacity-20" : "")
              }
            >
              {/* Sempre preto no branco: leitores de QR code erram com cores invertidas. */}
              <QRCodeSVG
                value={codigo.link}
                size={208}
                level="M"
                bgColor="#ffffff"
                fgColor="#000000"
                title="QR code para conectar o Telegram"
              />
            </div>
            {vencido ? (
              <p className="text-sm font-medium text-destructive">Este QR code venceu.</p>
            ) : (
              <p
                className="flex items-center gap-2 text-sm text-muted-foreground"
                aria-live="polite"
              >
                <Loader2 className="size-4 animate-spin" aria-hidden />
                Esperando a conexão… vale por {formatarRestante(restanteS)}
              </p>
            )}
            <div className="flex w-full items-start gap-3 rounded-lg bg-muted p-3 text-sm">
              <Smartphone className="mt-0.5 size-4 shrink-0" aria-hidden />
              <p>
                Está no celular? Toque em <strong>Abrir no Telegram</strong>. O bot é o{" "}
                <strong>@{codigo.usuario_bot}</strong>.
              </p>
            </div>
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          {novo ? (
            <Button onClick={aoFechar} className="w-full sm:w-auto">
              Fechar
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => gerarCodigo()} disabled={gerar.isPending}>
                <RefreshCw className="size-4" aria-hidden />
                Gerar outro
              </Button>
              {codigo && !vencido && (
                <Button asChild>
                  <a href={codigo.link} target="_blank" rel="noreferrer">
                    <ExternalLink className="size-4" aria-hidden />
                    Abrir no Telegram
                  </a>
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function formatarRestante(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
