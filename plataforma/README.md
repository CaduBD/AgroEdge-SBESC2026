# AgroEdge — Plataforma

Plataforma web do AgroEdge. Recebe por MQTT o que a BitDogLab mede e calcula, guarda,
mostra ao produtor e envia à placa a configuração do cultivo e comandos da válvula.
**Nenhum cálculo agronômico é feito aqui**: tudo isso roda na placa.

> Estado atual: **Fase 7 (integração com a placa)** concluída com a BitDogLab real **sem
> sensores** (clima fictício; ET₀, classificador e lâmina do firmware rodando na placa). Veja
> [placa_bancada/README.md](placa_bancada/README.md). Faltam os sensores e o MQTT no firmware
> definitivo.

## Painel (frontend)

Com o compose no ar, o painel fica em **http://localhost:8000** (no celular, no hotspot:
`http://<ip-do-notebook>:8000`). O login é o `ADMIN_EMAIL` / `ADMIN_SENHA` do `.env`.

Para desenvolver o frontend com recarga automática (o Vite repassa `/api` para a porta 8000):

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run typecheck    # tsc
npm run lint         # ESLint
npm test             # vitest (formatação pt-BR)
npm run format       # Prettier
```

Stack: Vite + React 19 + TypeScript, Tailwind CSS v4 + shadcn/ui, TanStack Query, React Router,
react-hook-form + zod, Recharts, date-fns (fuso America/Bahia), lucide-react e sonner.
O tema (cores da seção 12.2) fica em `frontend/src/index.css`; o Tailwind v4 não usa `tailwind.config.ts`.

## Como rodar

Pré-requisitos: Docker Desktop (com Compose) e Python 3.12+ no notebook.

Os comandos abaixo usam o `make`. No Windows sem `make`, use o script equivalente
`.\tarefas.ps1 <alvo>` (mesmos nomes de alvo).

```bash
make up      # cria .env (segredos aleatórios), mosquitto/passwd e sobe broker + app
make seed    # usuário do .env, token do chatbot, placa padrão, fazenda e cultivo de exemplo
make sim     # simulador acelerado: 3 dias de histórico em ~15 min, depois tempo real
```

No Windows:

```powershell
.\tarefas.ps1 venv   # uma vez: ambiente local para simulador, testes e lint
.\tarefas.ps1 up
.\tarefas.ps1 seed
.\tarefas.ps1 sim
```

- A senha de login (`ADMIN_SENHA`) e o token do chatbot (`CHATBOT_TOKEN`) ficam no `.env`.
- O app responde em `http://localhost:8000/api/saude`; a documentação em `/api/docs`.
- O banco SQLite fica no volume `app_data` (`/data/agroedge.db` no container).

### Comandos

| Comando | O que faz |
|---|---|
| `make env` | cria o `.env` a partir do `.env.example`, com segredos aleatórios (não sobrescreve) |
| `make passwd` | cria `mosquitto/passwd` com o usuário `plataforma` e a placa padrão |
| `make up` / `make down` / `make logs` | sobe, derruba, acompanha os logs |
| `make migrate` | aplica as migrações (o app já faz isso ao subir) |
| `make seed` | dados iniciais (idempotente) e publica a config retida da placa padrão |
| `make dispositivo SERIAL=agroedge-00002` | cadastra outra placa e imprime os dados para o `config_local.py` |
| `make sim` | simulador (mude os argumentos com `SIM_ARGS="..."`) |
| `make test` / `make lint` / `make fmt` | testes, lint/tipos, formatação |

## Simulador

`simulador/simulador.py` imita uma ou mais placas seguindo o contrato MQTT
(seção 7 da especificação). Exemplos, a partir de `plataforma/`:

```bash
python simulador/simulador.py                                  # placa padrão, tempo real
python simulador/simulador.py --dias 30 --acelerar 2000        # 30 dias de histórico rápido
python simulador/simulador.py --inicio 2026-11-01 --acelerar 96
python simulador/simulador.py --queda 02:00-04:00              # rede fora das 2h às 4h todo dia
python simulador/simulador.py --serial agroedge-00002 --senha SENHA
```

- **Relógio:** com `--inicio` (ou `--dias`), o tempo simulado começa nessa data e corre
  `--acelerar` vezes mais rápido até alcançar a hora real; depois segue em tempo real.
  O simulador nunca passa da hora real (o servidor rejeita `ts` mais de 24 h no futuro).
- **ET₀ e Kc:** o simulador importa `firmware/modelo/eto.py` e `culturas.py`, então ET₀ e Kc têm
  os mesmos números da placa (sem o firmware, cai num Penman-Monteith próprio). Classe e lâmina
  vêm de uma regra simples de balanço: o classificador MLP só roda na placa.
- O primeiro dia simulado costuma sair **incompleto** (sem classe), de propósito: começa no meio do dia.

## Cadastrar uma placa nova

Com o compose no ar:

```bash
make dispositivo SERIAL=agroedge-00002
# Windows: .\tarefas.ps1 dispositivo agroedge-00002
```

O script gera a senha MQTT, grava no `mosquitto/passwd`, cria o registro no banco, recarrega
o Mosquitto e imprime:

```
MQTT_HOST = "172.20.10.10"
MQTT_PORTA = 1883
MQTT_USUARIO = "agroedge-00002"
MQTT_SENHA = "…"
```

## Rede nos testes com a placa

- Hotspot do celular em **2,4 GHz**; notebook e placa conectados nele.
- **IP fixo no notebook** dentro da faixa do hotspot (no iPhone: `172.20.10.x`, ex.: `172.20.10.10`),
  igual ao `BROKER_HOST_PUBLICO` do `.env`.
- Liberar as portas **1883** e **8000** no firewall do notebook.
- Painel no celular: `http://<ip-do-notebook>:8000`.
- Ensaio antes do campo: placa conecta → desligar o hotspot por 2 h → religar → conferir se o
  atrasado aparece no Histórico sem buracos.

## API (para o painel e para o chatbot)

> **Desenvolvendo o chatbot?** Leia o [CHATBOT.md](CHATBOT.md): como subir a plataforma com o
> simulador, as rotas com exemplos reais, os eventos do SSE e como ler os dados reais da placa
> pelo Tailscale.

Documentação interativa: `http://localhost:8000/api/docs` (OpenAPI em `/api/openapi.json`).

- **Autenticação:** cookie de sessão (`POST /api/auth/login`) **ou** cabeçalho
  `Authorization: Bearer <CHATBOT_TOKEN>`. O token só enxerga os dados do seu usuário.
- **Erros:** sempre `{"erro": "codigo_curto", "mensagem": "texto em pt-BR"}`.
  Recurso de outro usuário responde 404, igual a inexistente.
- **Datas:** ISO 8601 UTC com `Z`; campos `ts` em Unix (segundos). Parâmetros `de`/`ate`
  aceitam `AAAA-MM-DD` (dia local, America/Bahia; `ate` inclui o dia) ou ISO 8601.

Rotas mais usadas pelo chatbot:

```bash
TOKEN=...   # CHATBOT_TOKEN do .env
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/fazendas
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/fazendas/1/cultivos
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/cultivos/1/resumo        # "/hoje"
curl -H "Authorization: Bearer $TOKEN" "localhost:8000/api/cultivos/1/diarios?de=2026-11-01"
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/cultivos/1/irrigacoes
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -X POST localhost:8000/api/dispositivos/agroedge-00001/comandos -d '{"acao":"abrir","minutos":10}'
curl -N -H "Authorization: Bearer $TOKEN" localhost:8000/api/stream             # alertas (SSE)
```

Eventos do SSE (`event:` + `data:` em JSON com `serial` e `cultivo_id`): `leitura`, `diario`,
`irrigacao`, `status`, `config_aplicada`, `comando`. A cada 25 s chega um evento `ping`: se o
cliente ficar ~60 s sem receber nada, a conexão caiu e ele deve reconectar.

Se o chatbot rodar dentro de um navegador, libere a origem dele em `CORS_ORIGENS` no `.env`.

## Conferir o banco

```bash
docker compose exec app python -c "import sqlite3; c=sqlite3.connect('/data/agroedge.db'); \
print(c.execute('select count(*), min(ts), max(ts) from leituras').fetchone()); \
print(c.execute('select data, classe, lamina_bruta from diarios order by data').fetchall()); \
print(c.execute('select motivo from mensagens_rejeitadas order by id desc limit 5').fetchall())"
```

## Estrutura

```
plataforma/
├── docker-compose.yml, Makefile, tarefas.ps1, .env.example
├── mosquitto/          mosquitto.conf, acl (padrão %u), passwd (gerado, fora do git)
├── backend/            FastAPI, ingestor MQTT, SQLModel + Alembic, scripts, testes
└── simulador/          simulador de placas
```

## Ajustes depois da Fase 7

- **Intervalo de telemetria pelo painel** (tela Dispositivo, card "Configuração da placa", ou
  `PATCH /api/dispositivos/{serial}`): de 1 a 60 min. Com a placa instalada, gera nova versão da
  config, e a tela mostra "Aguardando a placa…" até ela confirmar.
- **Toast "Configuração aplicada" que se perdia:** com a aba em segundo plano, o stream fecha
  depois de 15 s e o evento da placa não chega. Agora a própria tela avisa quando vê a mudança de
  "Aguardando" para "Aplicado", e o aviso sai uma vez só, venha do evento ou da tela. Testado
  com a placa real e a aba escondida.
- **Painel mais leve:** cada tela carrega só quando é aberta, e o gráfico do Início vem depois dos
  cards. A primeira abertura caiu de ~434 KB para ~211 KB comprimidos.

## Fase 7: o que foi testado com a placa real

BitDogLab (Pico W, MicroPython 1.29) no Wi-Fi 2,4 GHz, falando com o broker do notebook, com o
programa de [placa_bancada/](placa_bancada/README.md):

| Teste | Resultado |
|---|---|
| Wi-Fi + NTP; `ts` em UTC (o RTC da placa fica em hora local) | ok |
| Telemetria a cada 60 s; pill "Ao vivo" com o sinal Wi-Fi real | ok |
| Config retida ao conectar e mudança ao vivo (solo → Arenoso, v2) | ok: confirmada 54 s depois |
| Comando "abrir 1 min" → relé GPIO19 liga e desliga; `cmd_resp` e `irrigacao` | ok |
| Fechamento do dia na placa (ET₀, Kc, MLP, lâmina) | ok: classe 1 pediu 23,9 mm, a placa irrigou sozinha e o déficit voltou a 2 mm |
| Broker fora por 3 min: buffer e reenvio (mais recente primeiro, depois o atrasado) | ok: sem buracos, leituras a cada 60 s |
| Placa muda (sem fechar a conexão): LWT | ok: "Sem contato" em 93 s, com a hora real do último contato |
| Desligamento limpo (Ctrl+C) | ok: "offline" na hora |

Defeitos que só apareceram na placa e foram corrigidos: JSON cortado no `umqtt.simple` com
texto acentuado (publicar bytes), primeiro dia fechando ao ligar (tempos medidos antes do NTP) e
placa travando ~30 s a cada tentativa de reconexão com o broker fora (tempo-limite de 5 s e
intervalo crescente entre tentativas).

Não testado ainda: sensores reais e o ensaio de 2 h com o hotspot desligado (seção 14.5); o de
3 min com o broker fora cobre o mesmo caminho do código.

## Decisões da fase 6 que vale conhecer

- **Cultivos:** lista agrupada por fazenda (criar, renomear e excluir fazenda sem cultivos;
  arquivar cultivo, com opção de mostrar arquivados). Formulário em página própria
  (`/cultivos/novo` e `/cultivos/:id/editar`) com TAW e RAW calculados ao vivo e aviso fora de
  25–140 mm. O botão vira "Salvar e enviar à placa" quando há placa instalada, e o estado
  passa de "Aguardando a placa… (vN)" para "Aplicado na placa (vN)" pelo SSE.
- A confirmação de uma config nova chega com a próxima telemetria da placa (até 15 min no
  intervalo padrão), como manda o contrato.
- **Dispositivo:** seletor de placa (aparece quando há mais de uma), status, instalação atual,
  "Instalar em outro cultivo" (cultivos com outra placa ficam bloqueados; início no passado
  avisa que as leituras serão reatribuídas), comandos, histórico de instalações, mensagens
  rejeitadas e o bloco para o `config_local.py`. A senha MQTT não é mostrada: ela não fica
  guardada no servidor.
- **Comando expirado:** se a placa responder depois (ex.: voltou e recusou o comando vencido),
  o estado continua "Expirado" e a resposta fica registrada ("Recusado: chegou vencido").
- A válvula continua sendo aberta pela tela Início; a tela Dispositivo mostra o histórico.

## Decisões da fase 5 que vale conhecer

- O painel assina `/api/stream` e, a cada evento, atualiza só as consultas afetadas (agrupando
  rajadas, como o envio do atrasado do buffer). Toasts: novo fechamento ("irrigar X mm"),
  configuração aplicada na placa e resposta/expiração de comandos.
- **Primeiro envio imediato:** o stream manda um comentário logo ao conectar. Sem isso, proxies
  (o do Vite, e o Caddy no futuro) seguram os cabeçalhos e o navegador fica "conectando".
- **Vigia de silêncio:** o ping vai como evento nomeado e o painel reconecta se ficar 60 s sem
  receber nada. Isso cobre conexões "zumbi" (o proxy do Vite não avisa o navegador quando o
  backend reinicia). Ao reconectar, tudo é atualizado, porque eventos perdidos não voltam.
- **Aba em segundo plano** solta a conexão depois de 15 s e reconecta ao voltar: o navegador só
  abre 6 conexões por servidor, e cada aba aberta prenderia uma.
- O "offline" publicado pelo broker (LWT) não conta mais como contato da placa: a pill mostra
  "Sem contato desde" a hora real do último contato.
- Medido: derrubar o simulador encerrando o processo → "Sem contato" em ~2 s (o sistema fecha a
  conexão). Rede sumindo sem avisar (container congelado, como hotspot desligado) → 83 s, pelo
  keepalive do MQTT (60 s × 1,5).

## Decisões da fase 4 que vale conhecer

- Período, aba e variáveis do Histórico ficam na URL (`?periodo=30d&aba=fechamentos`), então
  dá para mandar o link de uma visão específica.
- Clima: um gráfico por variável (unidades diferentes não dividem eixo). Bateria e sinal Wi-Fi
  também podem ser escolhidos, para diagnóstico da placa.
- Lacunas (regra 9.7): faixa cinza "sem contato" e a linha interrompida. Quando o atrasado do
  buffer chega, a lacuna some na próxima consulta.
- Fechamentos: além de chuva, irrigação e ETc, o gráfico mostra a lâmina indicada (tracejada),
  para comparar o que a placa pediu com o que foi aplicado no dia seguinte.
- O CSV do Excel saiu com cabeçalhos em português, unidades e rótulos (Concluída, Déficit
  moderado…). Conferido abrindo no Excel: colunas separadas, números e datas reconhecidos.

## Decisões da fase 3 que vale conhecer

- **React 19 e Tailwind v4** (a especificação citava React 18 e `tailwind.config.ts`): os
  componentes atuais do shadcn/ui e do 21st.dev são feitos para essas versões. Decidido com a equipe.
- Os componentes vêm do shadcn/ui, adaptados às cores e fontes da seção 12.2. Nenhum componente
  do 21st.dev foi trazido ainda: os do shadcn cobriram tudo sem dependências extras.
- Tema claro/escuro: segue o sistema por padrão; a escolha feita em Conta fica no navegador.
- Até a fase 5 (SSE no painel), a tela Início se atualiza sozinha a cada minuto.
- O banner "Sem conexão com o servidor" aparece quando a API não responde e some sozinho
  quando ela volta (as consultas tentam de novo com espera crescente).
- A tela Conta (dados, tema e troca de senha) já está pronta.
- O Dockerfile agora tem dois estágios: Node gera o build do Vite e o FastAPI serve os arquivos.

## Decisões da fase 2 que vale conhecer

- `dispositivos.usuario_id` é o dono da placa (nulo = ainda não ativada). O seed e o
  `criar_dispositivo` ligam a placa ao usuário do `.env`; a migração 0002 fez o mesmo com as já existentes.
- Um cultivo tem **no máximo uma placa** instalada por vez (`cultivo_ocupado`). Arquivar um
  cultivo com placa é recusado: instale a placa em outro cultivo antes.
- Ao instalar com início no passado, **leituras, diários e irrigações** desde esse início vão para
  a nova instalação (a regra 9.2 vale para os três). O início não pode cair antes do início da
  instalação atual da placa (períodos não se sobrepõem).
- A confirmação de `cfg_v` vale para a instalação que a placa informa em `instalacao_id`
  (senão, a do período). Assim, leituras antigas do buffer não confirmam a instalação errada.
- Nas texturas pré-definidas, `agua_disp` vem do preset (apêndice B) e `raiz_m` fica nulo
  (padrão da cultura); só em `avancado` os dois valem como digitados.
- Mudar só o nome do cultivo não gera nova versão de config; qualquer outro campo gera.
- Config salva com o broker fora fica guardada em `config_publicada`; o ingestor republica as
  configs ativas sempre que (re)conecta ao broker.
- Comando é gravado antes de ser publicado (a resposta pode chegar muito rápido); sem broker,
  a API responde 503 e o comando não fica no histórico.
- Na tela Dispositivo, as mensagens rejeitadas listadas são as do próprio serial.
- Migrações do Alembic rodam com as chaves estrangeiras do SQLite desligadas (o batch recria tabelas).

## Decisões da fase 1 que vale conhecer

- O compose monta a pasta `mosquitto/` inteira em `/mosquitto/config` (e não arquivo por
  arquivo): o `mosquitto_passwd` reescreve o `passwd` trocando o arquivo, o que quebraria um
  bind mount de arquivo único ao cadastrar placas com o broker no ar.
- O `.env` ganhou `DISPOSITIVO_SERIAL` e `DISPOSITIVO_SENHA` (placa padrão do seed e do simulador).
- `cultivos` tem a coluna `exemplo` para marcar o cultivo criado pelo seed.
- O seed instala a placa padrão no cultivo de exemplo com início 30 dias atrás, para que o
  histórico simulado já caia numa instalação.
- O Dockerfile ainda só tem o estágio Python; o estágio do frontend entra na fase 3.
