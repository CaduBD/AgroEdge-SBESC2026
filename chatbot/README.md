# Chatbot do AgroEdge (Telegram)

Leva ao produtor, pelo Telegram, o que a placa calcula na lavoura: estado hídrico, lâmina
de irrigação indicada, clima, válvula e alertas automáticos. O bot só conversa com a
**API REST** e o **SSE** da plataforma (veja [`plataforma/CHATBOT.md`](../plataforma/CHATBOT.md));
não fala MQTT, não lê o banco e **não recalcula nada agronômico**.

## O que o produtor pode fazer

| Botão ou texto | O que acontece |
|---|---|
| **Hoje** (`/hoje`) | Estado hídrico, lâmina indicada (mm, L/planta, minutos de válvula), ET₀/ETc/Kc, clima agora, válvula e placa |
| **Válvula** (`/valvula`) | Botões *Abrir 5/10/20/30 min*, *Abrir N min (indicado)* e *Fechar*. **Sempre pede confirmação** |
| `abrir 10` / `fechar` | O mesmo, escrito |
| **Histórico** (`/historico`) | Fechamentos diários dos últimos 7 dias |
| **Irrigações** (`/irrigacoes`) | Irrigações dos últimos 7 dias (automáticas e manuais) |
| **Cultivos** (`/cultivos`) | Escolhe o cultivo (cada conversa lembra o seu) |
| **Alertas** (`/alertas`) | Liga ou desliga os alertas nesta conversa |
| `/desconectar` | Tira a conversa da conta (com confirmação) |

Alertas automáticos (vêm do SSE):

- **Fechamento do dia** (meia-noite): estado hídrico e quanto irrigar, com botões *Ver hoje* e *Válvula*;
- **Placa sem contato / voltou** (só quando muda);
- **Irrigação começou / terminou**;
- **Resposta da placa** a um comando pedido pelo bot (executado, recusado ou expirado).

Segurança:

- só usa o bot quem **conectou a conversa pelo painel** (Conta → Telegram → QR code); as
  outras conversas só recebem a explicação de como conectar;
- cada conversa age como a conta que a conectou: vê só os cultivos dela e só abre as
  válvulas dela (a plataforma aplica as mesmas regras de posse do painel);
- abrir a válvula pede confirmação; o botão *Sim, abrir* vale 2 minutos e não envia duas
  vezes se for tocado de novo;
- o serial da placa vem sempre do `/resumo` do cultivo (nada de IDs ou seriais fixos).

## 1. Criar o bot no Telegram (uma vez)

1. No Telegram, abra uma conversa com **@BotFather** e mande `/newbot`.
2. Escolha o nome (ex.: *AgroEdge*) e o usuário, que precisa terminar em `bot`
   (ex.: `agroedge_sbesc_bot`).
3. O BotFather responde com o **token** (algo como `7012345678:AAH...`). Ele é a senha do
   bot: não coloque no git nem mande em grupo.

## 2. Instalar

Pré-requisito: Python 3.12+.

Windows (PowerShell), a partir de `chatbot/`:

```powershell
.\tarefas.ps1 venv        # cria .venv, instala e copia .env.exemplo para .env
```

Linux/macOS: `make venv`.

Preencha o `chatbot/.env`:

```bash
AGROEDGE_API_URL=http://localhost:8000     # ou o IP Tailscale do notebook da equipe
AGROEDGE_TOKEN=...                         # CHATBOT_TOKEN do plataforma/.env escolhido
TELEGRAM_BOT_TOKEN=...                     # do @BotFather
```

## 3. Testar sem Telegram

Com a plataforma e o simulador rodando (`make up`, `make seed`, `make sim` em `plataforma/`):

```powershell
.\tarefas.ps1 verificar   # confere a API e o token, lista os cultivos
.\tarefas.ps1 console     # conversa no terminal: escreva "hoje", "valvula", "abrir 5"...
```

O modo console não usa QR code: a conversa do terminal age como o dono do token. Nele os
botões aparecem numerados (digite o número para "tocar") e os alertas
do SSE aparecem no meio da conversa. Abrir a válvula no console manda o comando de verdade
(para o simulador, se a plataforma for a sua local).

## 4. Rodar o bot

```powershell
.\tarefas.ps1 bot
```

Ao ligar, o bot informa o seu @ à plataforma. A partir daí, cada produtor conecta o
próprio Telegram **pelo painel**, sem mexer em nenhum arquivo:

1. No painel, abra **Conta** e, no cartão **Telegram**, toque em **Conectar Telegram**.
2. Aparece um QR code (vale 10 minutos). Aponte a câmera do celular para ele, ou toque em
   *Abrir no Telegram* se estiver no celular.
3. O Telegram abre a conversa com o bot e manda `/start <código>`. O bot responde
   "Pronto! Esta conversa está conectada à conta de …" e o painel mostra **conectado**.
4. Mande `Hoje`.

No mesmo cartão o produtor vê as conversas conectadas e pode **desconectar** qualquer uma.
Uma conta pode ter várias conversas (o celular do produtor, o do gerente, um grupo).

O bot usa *long polling*: ele mesmo busca as mensagens no Telegram. Por isso roda em
qualquer computador com internet, inclusive o notebook da equipe, **sem IP público,
domínio ou HTTPS**. Para usar os dados reais da placa de outro computador, use o Tailscale
(CHATBOT.md, seção 6) e aponte `AGROEDGE_API_URL` para o notebook.

Na demonstração, o mais simples é rodar o bot **no próprio notebook da equipe**, com
`AGROEDGE_API_URL=http://localhost:8000`.

Só pode haver **um** processo do bot por token do Telegram. Se dois integrantes rodarem
ao mesmo tempo com o mesmo token, o Telegram reclama (`Conflict: terminated by other
getUpdates request`). Para desenvolver em paralelo, cada um cria o seu bot de teste no
@BotFather.

## Configuração

| Variável | Padrão | Para quê |
|---|---|---|
| `AGROEDGE_API_URL` | `http://localhost:8000` | Plataforma (local ou do notebook da equipe) |
| `AGROEDGE_TOKEN` | — | `CHATBOT_TOKEN` do `.env` da plataforma escolhida |
| `TELEGRAM_BOT_TOKEN` | — | Token do @BotFather |
| `TELEGRAM_PROXY` | vazio | Proxy HTTP(S) para o Telegram, se a rede exigir |
| `BOT_ALERTAS` | `diario,status,irrigacao` | Tipos de alerta automático |
| `BOT_ARQUIVO_ESTADO` | `estado_bot.json` | Alertas já enviados (para não repetir) |
| `BOT_FUSO` | `America/Bahia` | Fuso dos horários (a API manda UTC) |

Quem pode usar o bot, o cultivo escolhido e se cada conversa quer alertas ficam **na
plataforma** (tabela `vinculos_canal`). O `estado_bot.json` só guarda a data do último
fechamento já avisado e o último status de cada placa: ao reiniciar (ou quando o SSE cai e
volta), o bot compara com o `/resumo` e manda o alerta do fechamento que perdeu. Apagar o
arquivo é seguro. Ele não vai para o git.

Como o bot fala com a plataforma (detalhes em `plataforma/CHATBOT.md`, seção 8):

- usa o token do chatbot (escopo `chatbot`) e, em cada pedido de uma conversa, o cabeçalho
  `X-Conversa: telegram:<chat id>`; a API responde como a conta dona da conversa;
- ouve `GET /api/stream?todos=true`: chegam os eventos de todas as contas, com
  `usuario_id`, e o bot manda cada alerta só para as conversas daquela conta.

## Organização

```
chatbot/
  agroedge_bot/
    nucleo/            independente de canal
      api.py           cliente da API REST (httpx)
      sse.py           ouvinte do SSE: reconexão, timeout de 70 s, recuperação
      servico.py       entende os pedidos, válvula com confirmação, alertas
      textos.py        textos em pt-BR (números com vírgula, horário local)
      mensagens.py     Resposta (texto + botões), sem Telegram
      acesso.py        quem pode usar e o que cada conversa escolheu (plataforma ou local)
      estado.py        o que o bot lembra entre reinícios
    canais/
      telegram.py      adaptador aiogram (long polling)
      console.py       adaptador de terminal (testes e desenvolvimento)
    __main__.py        python -m agroedge_bot [--console | --verificar]
  tests/               pytest com plataforma e Telegram falsos (sem rede)
```

O **núcleo** recebe texto ou o dado de um botão e devolve uma `Resposta` (texto com
`<b>`/`<i>` e botões). O **canal** só traduz isso para a plataforma de mensagens. Para
acrescentar o WhatsApp (pela Cloud API oficial da Meta), basta um `canais/whatsapp.py`
que:

1. receba o webhook da Meta e chame `servico.tratar_texto(numero, texto)` ou
   `servico.tratar_botao(numero, id_do_botao)`;
2. envie a `Resposta` convertendo a marcação com `para_texto_simples()` e os botões em
   *reply buttons* (até 3) ou *list messages*;
3. ofereça `enviar(numero, resposta)` para os alertas (no WhatsApp, fora da janela de 24 h,
   isso exige *templates* aprovados pela Meta).

Nada no núcleo muda. O console é a prova: é um segundo canal usando o mesmo núcleo.

## Desenvolvimento

```powershell
.\tarefas.ps1 test     # testes sem rede (plataforma e Telegram falsos)
.\tarefas.ps1 lint     # ruff + mypy
.\tarefas.ps1 fmt
```

Limitações conhecidas:

- se o bot reiniciar enquanto espera a resposta da placa a um comando, essa resposta não é
  avisada no chat (o comando continua valendo; o resultado aparece no painel e no *Hoje*).
