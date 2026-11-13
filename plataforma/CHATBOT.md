# Guia para o chatbot do AgroEdge

Este guia é para quem desenvolve o chatbot. Ele explica como o bot conversa com a plataforma,
como trabalhar com dados simulados no seu computador e como ler os dados reais da placa.

> **Resumo:** o bot fala **só com a API REST** da plataforma (e com o SSE para alertas).
> Ele **não** fala MQTT com a placa e **não** acessa o banco de dados diretamente.

## 0. Produção (desde 13/11/2026)

A plataforma está na VPS, em **https://agroedge.tech**, com os dados reais: a placa de bancada
manda para lá e o histórico do notebook foi levado junto. **O bot de verdade roda na própria
VPS**, como serviço do Docker (`chatbot` no `docker-compose.prod.yml`). Ele fala com a API pela
rede interna (`http://app:8000`) e usa o `CHATBOT_TOKEN` do `.env` do servidor.

| Para | Use |
|---|---|
| API real (testar com dados reais) | `https://agroedge.tech/api` com o `CHATBOT_TOKEN` da VPS, que o dono te passa por mensagem privada |
| Documentação | `/api/docs` do Docker no seu computador (na VPS a página pede login). Na VPS: `GET https://agroedge.tech/api/openapi.json` com o token |
| Desenvolver | A plataforma no seu computador com o simulador (seção 2) |

**Não rode o bot de produção no seu computador.** O Telegram entrega cada mensagem a um só, então
dois processos com o mesmo token roubam as mensagens um do outro. Para desenvolver, crie um
segundo bot no @BotFather, só de teste.

**Atualizar o bot na VPS:** depois do merge na `main`, quem tem a chave SSH roda no notebook
`bash plataforma/producao/enviar.sh`. Ele envia `plataforma/` e `chatbot/` e reconstrói o bot. O
token do Telegram é configurado uma vez com `bash plataforma/producao/configurar_chatbot.sh`.

---

## 1. Como os dados ficam "iguais" para todo mundo

Existe **um único banco de verdade**: o da plataforma ligada à placa (hoje, o notebook da
equipe). A placa manda os dados para um broker só, e só esse banco recebe as leituras reais.

```
 BitDogLab ──MQTT──► notebook da equipe (plataforma + banco REAL) ◄──API── bot (dados reais)

 seu computador: plataforma + simulador (banco de TESTE) ◄──API── bot (desenvolvimento)
```

- **Código** é compartilhado pelo git (mesmo repositório).
- **Dados** nunca são copiados nem mesclados entre computadores. Para ver dados reais, o bot
  **aponta para a API do notebook da equipe** (seção 6). Para desenvolver, usa a sua cópia local
  com o simulador. A API é a mesma nos dois lugares, então o que funciona com o simulador
  funciona com a placa.

O bot só precisa de duas configurações (sugestão de nomes de variáveis de ambiente):

```bash
AGROEDGE_API_URL=http://localhost:8000      # sua plataforma local, ou a da equipe (seção 6)
AGROEDGE_TOKEN=...                           # CHATBOT_TOKEN do .env da plataforma escolhida
```

---

## 2. Subir a plataforma no seu computador (dados simulados)

Pré-requisitos: Docker Desktop e Python 3.12+.

```bash
cd plataforma
make up      # cria .env com segredos aleatórios, sobe broker + API + painel
make seed    # usuário, token do chatbot, placa, fazenda e cultivo de exemplo
make sim     # simulador: 3 dias de histórico em ~15 min, depois tempo real
```

No Windows sem `make`, use `.\tarefas.ps1 venv` (uma vez) e depois `.\tarefas.ps1 up`,
`.\tarefas.ps1 seed`, `.\tarefas.ps1 sim`.

- Painel: http://localhost:8000 (login: `ADMIN_EMAIL` / `ADMIN_SENHA` do seu `plataforma/.env`).
- **Documentação interativa da API: http://localhost:8000/api/docs** (botão *Authorize* aceita o token).
- Seu token: a linha `CHATBOT_TOKEN=` do seu `plataforma/.env`.
- Mais histórico de uma vez: `python simulador/simulador.py --dias 30 --acelerar 2000`.

---

## 3. Autenticação e formato

- Toda chamada leva o cabeçalho `Authorization: Bearer <token>`.
- Token errado ou ausente: `401 {"erro": "token_invalido", ...}`.
- O token só enxerga os dados do usuário dono dele. Recurso de outro usuário responde `404`.
  Com o cabeçalho `X-Conversa: telegram:<chat id>`, o token do chatbot age como o usuário
  que conectou aquela conversa pelo painel (seção 8).
- Datas e horas vêm em **ISO 8601 UTC** (`2026-11-11T23:00:00Z`); campos `ts` em **Unix
  (segundos)**. Para mostrar ao produtor, converta para **America/Bahia (UTC−3)**.
- Datas de dia (`data`, `data_referencia`) são do dia **local** (`AAAA-MM-DD`), sem conversão.
- Parâmetros `de`/`ate` aceitam `AAAA-MM-DD` (dia local; `ate` inclui o dia todo) ou ISO 8601.
- Erros sempre assim, com `mensagem` pronta para mostrar ao usuário:

```json
{"erro": "nao_encontrado", "mensagem": "Cultivo não encontrado."}
```

---

## 4. Rotas que o bot mais usa

Exemplos reais, encurtados. A lista completa e todos os campos estão em `/api/docs`.

### Descobrir fazendas e cultivos (nunca fixe IDs no código)

Os IDs mudam de um banco para outro: o cultivo 2 no notebook pode ser o 5 no seu computador.
Sempre descubra pelo caminho fazendas → cultivos.

```bash
curl -H "Authorization: Bearer $AGROEDGE_TOKEN" $AGROEDGE_API_URL/api/fazendas
```
```json
[{"id": 1, "nome": "Fazenda Exemplo", "municipio": "Petrolina - PE", "n_cultivos": 2, "...": "..."}]
```

```bash
curl -H "Authorization: Bearer $AGROEDGE_TOKEN" $AGROEDGE_API_URL/api/fazendas/1/cultivos
```
```json
[{"id": 2, "nome": "Bancada uva", "cultura": "uva_italia", "dia_do_ciclo": 22,
  "ultima_classe": 0, "taw_mm": 66.0, "raw_mm": 23.1,
  "configuracao": {"serial": "agroedge-00001", "instalacao_id": 4, "cfg_v": 1,
                   "cfg_v_aplicada": 1, "aplicada": true}}]
```

### "/hoje": tudo de um cultivo num só pedido

```bash
curl -H "Authorization: Bearer $AGROEDGE_TOKEN" $AGROEDGE_API_URL/api/cultivos/2/resumo
```

Chaves: `cultivo`, `dispositivo`, `ultima_leitura`, `ultimo_diario`, `ciclo`, `valvula`,
`ultimos_7_dias`. As mais úteis para o bot:

```json
{
  "ultimo_diario": {"data": "2026-11-10", "classe": 0, "lamina_bruta": 11.9, "minutos": 357.0,
                    "aplicar_l_planta": 47.6, "et0": 6.28, "etc": 4.27, "kc": 0.68, "avisos": []},
  "dispositivo": {"serial": "agroedge-00001", "status": "ao_vivo",
                  "ultima_telemetria": "2026-11-11T23:00:00Z", "ultimo_contato": "2026-11-11T23:00:42Z",
                  "rssi": -61, "bat_v": null, "cfg_aplicada": true},
  "ultima_leitura": {"ts": 1794438000, "temp_c": 31.6, "ur_pct": 47.5, "vento_ms": 4.2,
                     "rad_wm2": 0.0, "chuva_mm": 0.0},
  "ciclo": {"dias": 22, "ciclo_dias": 109, "fora_do_ciclo": false, "fase": null, "fase_nome": null},
  "valvula": {"aberta": false, "proxima_prevista": "2026-11-12T08:00:00Z",
              "ultima": {"ts_inicio": 1794430245, "minutos": 1.0, "mm": 0.03, "origem": "manual"}}
}
```

Como ler:

- **Lâmina de hoje** = `ultimo_diario.lamina_bruta` (mm), `aplicar_l_planta` (litros por planta)
  e `minutos` (de válvula). Tudo calculado **na placa**: o bot só repassa, não recalcula.
- **Estado hídrico** = `ultimo_diario.classe`: `0` Adequado, `1` Déficit moderado,
  `2` Déficit crítico, `null` Sem classe (veja `avisos`).
- **Placa** = `dispositivo.status`: `ao_vivo`, `atrasado`, `sincronizando` ou `sem_contato`.
  `dispositivo` é `null` quando o cultivo não tem placa instalada.
- `ultimo_diario` é `null` antes do primeiro fechamento (a placa fecha o dia à meia-noite).

### Histórico

```bash
curl -H "Authorization: Bearer $AGROEDGE_TOKEN" "$AGROEDGE_API_URL/api/cultivos/2/diarios?de=2026-11-01"
curl -H "Authorization: Bearer $AGROEDGE_TOKEN" "$AGROEDGE_API_URL/api/cultivos/2/irrigacoes?de=2026-11-01"
curl -H "Authorization: Bearer $AGROEDGE_TOKEN" "$AGROEDGE_API_URL/api/cultivos/2/leituras?de=2026-11-10&variaveis=temp_c,chuva_mm"
```

Sem `de`/`ate`, diários e irrigações trazem os últimos 30 dias; leituras, os últimos 7.
Irrigação: `origem` (`automatica`/`manual`), `estado` (`iniciada`, `concluida`, `cancelada`,
`interrompida`), `minutos` e `mm` reais.

### Válvula (comandos manuais)

```bash
curl -X POST -H "Authorization: Bearer $AGROEDGE_TOKEN" -H "Content-Type: application/json" \
     -d '{"acao": "abrir", "minutos": 10}' \
     $AGROEDGE_API_URL/api/dispositivos/agroedge-00001/comandos
```
```json
{"id": "4b77405e-…", "acao": "abrir", "minutos": 10.0, "estado": "enviado",
 "criado_em": "2026-11-11T22:42:23Z", "valido_ate": "2026-11-11T22:52:23Z",
 "resultado": null, "respondido_em": null}
```

- `acao`: `abrir` (exige `minutos` de 1 a 120) ou `cancelar` (fecha a válvula).
- O serial vem de `resumo.dispositivo.serial` (ou `cultivo.configuracao.serial`).
- A resposta da placa chega depois: pelo SSE (evento `comando`) ou em
  `GET /api/dispositivos/{serial}/comandos`. Estados: `enviado`, `executado`, `recusado`, `expirado`.
- O comando vale **10 minutos**; sem resposta nesse tempo, vira `expirado`.
- Erros que o bot deve tratar:
  - `409 dispositivo_offline`: placa sem contato há mais de 10 min (o comando não chegaria);
  - `400 minutos_invalidos`;
  - `503 sem_broker`: a plataforma está sem conexão com o broker MQTT (tente de novo).

---

## 5. Alertas em tempo real (SSE)

`GET /api/stream` com o mesmo token. A conexão fica aberta e chegam eventos assim:

```
event: diario
data: {"serial": "agroedge-00001", "cultivo_id": 2, "data": "2026-11-10", "lamina_bruta": 11.9, "minutos": 357.0, "classe": 0}
```

| Evento | Quando | Campos além de `serial` e `cultivo_id` |
|---|---|---|
| `diario` | fechamento do dia (meia-noite) | `data`, `lamina_bruta`, `minutos`, `classe` |
| `status` | placa conectou ou caiu | `status` (`online` / `offline`) |
| `comando` | placa respondeu ou o comando expirou | `id`, `estado`, `resultado` |
| `irrigacao` | irrigação começou ou terminou | `id`, `estado`, `origem`, `minutos` |
| `leitura` | chegou telemetria | `n`, `buf` |
| `config_aplicada` | placa confirmou a configuração | `instalacao_id`, `cfg_v` |
| `ping` | a cada 25 s | nenhum |

Regras para o cliente:

- Logo ao conectar chega um comentário (`: conectado`) e `retry: 3000`.
- **Se ficar ~60 s sem receber nada (nem `ping`), a conexão morreu: reconecte.**
- Eventos perdidos enquanto o bot estava desconectado **não voltam**: depois de reconectar,
  consulte `/resumo` dos cultivos de interesse.
- O bot só recebe eventos de placas e cultivos do usuário dono do token. Com
  `GET /api/stream?todos=true` (só o token do chatbot), chegam os eventos de **todas** as
  contas; cada `data` traz `usuario_id`, para o bot avisar só as conversas daquela conta.

Exemplo em Python (com `httpx`), só para mostrar o formato:

```python
import json, os, httpx

url = os.environ["AGROEDGE_API_URL"] + "/api/stream"
cabecalhos = {"Authorization": f"Bearer {os.environ['AGROEDGE_TOKEN']}"}

with httpx.stream("GET", url, headers=cabecalhos, timeout=httpx.Timeout(70, connect=10)) as r:
    evento = None
    for linha in r.iter_lines():          # timeout de 70 s: sem ping = reconectar
        if linha.startswith("event:"):
            evento = linha[6:].strip()
        elif linha.startswith("data:") and evento not in (None, "ping"):
            dados = json.loads(linha[5:])
            if evento == "diario":
                print(f"Novo fechamento: irrigar {dados['lamina_bruta']} mm")
            elif evento == "status" and dados["status"] == "offline":
                print(f"A placa {dados['serial']} ficou sem contato")
        elif linha == "":
            evento = None
```

---

## 6. Usar os dados reais (a plataforma do notebook da equipe)

Mesma rede (hotspot ou laboratório): use `AGROEDGE_API_URL=http://<ip-do-notebook>:8000`.

Cada um na sua casa: use o **Tailscale**, uma VPN gratuita que liga os computadores como se
estivessem na mesma rede. Só quem está na rede de vocês enxerga a plataforma.

**No notebook da equipe (uma vez):**

1. Instale o Tailscale (https://tailscale.com/download) e entre com uma conta.
2. Libere a porta 8000 no firewall do Windows (PowerShell como administrador):
   ```powershell
   New-NetFirewallRule -DisplayName "AgroEdge 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
   ```
3. Veja o endereço do notebook na rede Tailscale: `tailscale ip -4` (algo como `100.101.102.103`).
4. Convide o integrante do chatbot: no painel do Tailscale, *Share* da máquina, ou adicione o
   e-mail dele à sua rede (*Users → Invite*).
5. Mande para ele, por um canal **privado**, o `CHATBOT_TOKEN` do `plataforma/.env` do notebook.

**No computador do bot:**

1. Instale o Tailscale e entre com a conta que recebeu o convite.
2. Teste: `curl http://100.101.102.103:8000/api/saude` deve responder `{"ok": true, ...}`.
3. Configure o bot:
   ```bash
   AGROEDGE_API_URL=http://100.101.102.103:8000
   AGROEDGE_TOKEN=<token recebido>
   ```

Lembretes: o notebook precisa estar ligado, com `make up` rodando. Se o IP do notebook na rede
local mudar, o endereço do Tailscale **não** muda.

**Alternativa sem rede:** para testar com dados parecidos com os reais, a equipe pode mandar
uma cópia do banco. No notebook da equipe:

```bash
docker compose stop app
docker compose cp app:/data/agroedge.db ./agroedge.db
docker compose start app
```

No seu computador, com o arquivo recebido:

```bash
docker compose stop app
docker compose cp ./agroedge.db app:/data/agroedge.db
docker compose exec app rm -f /data/agroedge.db-wal /data/agroedge.db-shm   # se existirem
docker compose start app
```

(Parar o app antes garante que a cópia esteja completa.) É só uma cópia: nada do que acontecer
nela volta para o banco real, e o login e o token passam a ser os da equipe.

---

## 7. Cuidados

- **Confirme com o usuário antes de abrir a válvula** ("Abrir a válvula da Bancada uva por
  10 min?"). Abrir água é a única ação do bot com efeito físico.
- **Nunca fixe IDs nem seriais no código:** descubra pela API (seção 4).
- **Nunca coloque tokens no git.** Use variáveis de ambiente ou um `.env` do bot fora do
  repositório (o `chatbot/.gitignore` já ignora o `.env`).
- O bot **não recalcula** nada agronômico: lâmina, classe, ET₀ e Kc vêm da placa.
- Se o bot rodar **dentro de um navegador**, a equipe precisa liberar a origem dele em
  `CORS_ORIGENS` no `.env` da plataforma. Bot em servidor (Telegram, WhatsApp, Python) não precisa.
- Mudança na API? Peça à equipe da plataforma ou abra um pull request: a API é compartilhada
  com o painel.

---

## 8. Conversas conectadas pelo painel (QR code)

Quem pode usar o bot fica na plataforma, não no bot. Cada produtor conecta o próprio
Telegram pelo painel e, a partir daí, a conversa age como a conta dele.

```
 bot liga ── PUT /api/canais/telegram/bot {"usuario_bot": "agroedge_bot"}
 painel ──── Conta → Telegram → "Conectar Telegram"
             POST /api/canais/telegram/codigo → QR code de https://t.me/agroedge_bot?start=<codigo>
 celular ─── abre o link; o Telegram manda "/start <codigo>" ao bot
 bot ─────── POST /api/canais/telegram/vincular {"codigo", "conversa_id", "nome"}
 painel ──── GET /api/canais/codigos/<codigo> (a cada 2 s) → "conectado!"
 bot ─────── cada pedido daquela conversa leva  X-Conversa: telegram:<chat id>
```

Tabelas: `vinculos_canal` (conversa ↔ usuário, alertas, cultivo escolhido),
`codigos_vinculo` (código do QR, uso único, vale 10 min) e `bots_canal` (o @ do bot).
O token de serviço ganhou o campo `escopo`: `chatbot` (criado pelo seed) pode usar
`X-Conversa`, `?todos=true` no SSE e as rotas abaixo; `usuario` (padrão) não pode.

Rotas do painel (usuário logado):

| Rota | Para quê |
|---|---|
| `GET /api/canais/telegram` | `usuario_bot` do bot (nulo = bot nunca foi ligado) |
| `POST /api/canais/telegram/codigo` | gera o código e o `link` do QR code (`409 bot_desligado` sem bot) |
| `GET /api/canais/codigos/{codigo}` | se o código já foi usado e por qual conversa |
| `GET /api/canais/vinculos` | conversas conectadas da conta |
| `DELETE /api/canais/vinculos/{id}` | desconecta uma conversa |

Rotas do chatbot (token com escopo `chatbot`):

| Rota | Para quê |
|---|---|
| `PUT /api/canais/telegram/bot` | registra o @ do bot (o bot faz isso ao ligar) |
| `POST /api/canais/telegram/vincular` | troca o código pelo vínculo (`404 codigo_invalido`, `409 codigo_usado`, `410 codigo_expirado`) |
| `GET /api/canais/telegram/conversas` | todas as conversas vinculadas, com `usuario_id` e `alertas` |
| `GET/PATCH/DELETE /api/canais/conversa` | a conversa do `X-Conversa`: preferências (`alertas`, `cultivo_id`) e desconectar |

Conversa não conectada (ou desconectada pelo painel) responde
`403 conversa_nao_vinculada`: o bot então explica como conectar.

---

## 9. Organização no repositório

- O bot fica numa pasta própria na raiz, por exemplo `chatbot/`, ao lado de `plataforma/`.
- Trabalhe numa branch (`git checkout -b chatbot/primeira-versao`) e abra pull request para a
  `main`. Não altere `plataforma/`, `firmware/` nem `modelo/` sem combinar.
- Mensagens de commit em português, no padrão Conventional Commits (`feat(chatbot): ...`).
