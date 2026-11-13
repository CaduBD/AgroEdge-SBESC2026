# Produção (VPS)

A plataforma na internet: painel e API em `https://<domínio>` e o broker das placas em
`mqtt.<domínio>:8883` (TLS). Tudo em Docker, num Ubuntu 24.04.

```
internet ──443──► Caddy (HTTPS, Let's Encrypt) ──► app :8000 (API + painel + SSE)
                                                        │  rede interna do Docker
placas ───8883──► Mosquitto (TLS, senha por placa) ◄─1883┘
                  backup diário do banco ──► plataforma/backups/
```

Só as portas 22, 80, 443 e 8883 ficam abertas. O app (8000) e o broker sem TLS (1883) não
saem da rede interna do Docker.

| Arquivo | O que faz |
|---|---|
| `../docker-compose.prod.yml` | Os serviços da produção: caddy, mosquitto, app e backup |
| `Caddyfile` | HTTPS automático, cabeçalhos de segurança e o certificado de `mqtt.<domínio>` |
| `mosquitto.conf` | Broker: 1883 interna e 8883 com TLS, sem anônimos, limites contra abuso |
| `mosquitto-entrada.sh` | Copia o certificado do Caddy para o broker e reinicia o broker quando ele renova |
| `backup.sh` | Cópia consistente do SQLite na partida e todo dia às 03h (Petrolina); guarda 14 dias |
| `preparar_vps.sh` | Endurece um Ubuntu novo: firewall, fail2ban, SSH só por chave, swap e Docker |
| `enviar.sh` | Roda no notebook: envia o commit atual (`plataforma/` e `chatbot/`) para a VPS e sobe |
| `configurar_chatbot.sh` | Roda no notebook: grava o token do bot do Telegram no `.env` da VPS e liga o chatbot |

## Servidor atual

- Hostinger, Ubuntu 24.04, 1 vCPU, 4 GB de RAM e 50 GB de disco, IP `187.53.112.45`.
- Domínio `agroedge.tech`. No DNS, os registros A de `@`, `www` e `mqtt` apontam para o IP.
- Já preparado com o `preparar_vps.sh` em 13/11/2026.
- Acesso só por chave SSH. No notebook, a chave fica em `~/.ssh/agroedge_vps` e o atalho
  `agroedge-vps` está no `~/.ssh/config`. Sem a chave, entre pelo terminal do navegador no
  painel da Hostinger.

## Primeira subida

No notebook, no Git Bash, a partir de `plataforma/`:

```bash
bash producao/enviar.sh --primeira-vez agroedge.tech
```

O script faz quatro coisas:

1. Envia o commit atual para `/opt/agroedge/plataforma`.
2. Gera no próprio servidor o `.env` de produção, com segredos novos, e o `mosquitto/passwd`.
   Os segredos não passam pelo notebook.
3. Sobe tudo e roda o `seed`, que cria o usuário, o token do chatbot e a placa padrão.
4. Testa `https://agroedge.tech/api/saude`.

A senha de login do painel fica no `.env` do servidor. Só o dono deve ver:

```bash
ssh agroedge-vps "grep -E '^(ADMIN_EMAIL|ADMIN_SENHA)=' /opt/agroedge/plataforma/.env"
```

## Atualizar (o dia a dia)

Faça o commit no notebook e rode:

```bash
bash producao/enviar.sh
```

O script envia só o que está commitado e reconstrói o que mudou. As migrações rodam sozinhas na
partida do app. O `.env`, as senhas do broker e os backups do servidor não são tocados.

## Placas

- Para cadastrar uma placa nova no servidor, rode
  `ssh agroedge-vps "cd /opt/agroedge/plataforma && python3 backend/scripts/criar_dispositivo.py agroedge-00002"`.
  O script mostra o `config_local.py` com `MQTT_HOST = "mqtt.agroedge.tech"`, `MQTT_PORTA = 8883`
  e `MQTT_TLS = True`. O broker relê as senhas sem derrubar ninguém.
- O certificado é do Let's Encrypt (ECDSA). Em 13/11/2026 a cadeia era
  `mqtt.agroedge.tech ← YE1 ← Root YE ← ISRG Root X2`. A placa valida guardando a
  **ISRG Root X2** e precisa do RTC em UTC (veja `placa_bancada/README.md`).
- **Placa de bancada (`agroedge-00001`):** já fala com a VPS por TLS. Para gerar os arquivos,
  rode `python placa_bancada/preparar.py --vps`.
- **Simulador (`agroedge-00002`):** rode `python simulador/simulador.py --vps --dias 3 --acelerar 288`.
- A porta 1883 não fica aberta na internet.

## Chatbot do Telegram

Roda na VPS como serviço `chatbot` (perfil do compose), a partir da pasta `chatbot/`. Ele fala
com a API pela rede interna e com o Telegram por long polling, então não precisa de porta aberta.

Para configurar a primeira vez, ou trocar o token do bot, rode no notebook, no Git Bash:

```bash
bash producao/configurar_chatbot.sh
```

O script pede o token do @BotFather, sem mostrar na tela, e grava `TELEGRAM_BOT_TOKEN` e
`COMPOSE_PROFILES=chatbot` no `.env` da VPS. Depois, no painel, vá em **Conta → Telegram**,
informe o @ do bot e gere o QR code para conectar as conversas.

O mesmo bot não pode rodar em dois lugares: para desenvolver, use outro bot, de teste.

## Histórico do notebook (importado em 13/11/2026)

O banco do notebook foi copiado para a VPS, com 3.417 leituras de 11/10 a 13/11, 33
fechamentos e 10 irrigações. Da VPS ficaram a senha de login (a que o dono trocou) e o token do
chatbot. O banco que a VPS tinha antes ficou guardado:

- `backups/antes-da-importacao.db.gz`;
- `agroedge-vps-inicial.db`, dentro do volume.

Para repetir a importação:

1. Faça uma cópia consistente do banco do notebook (`sqlite3 .backup`).
2. Com o app parado, troque o arquivo no volume `app_data`.
3. Rode o SQL que copia `usuarios.senha_hash`, `usuarios.sessao_versao` e `tokens_servico` do banco
   antigo da VPS.

Todo `docker compose exec` dentro de um `ssh ... bash -s` precisa de `</dev/null`. Sem isso, ele
lê o resto do script como entrada e os passos seguintes não rodam.

## Comandos úteis (no servidor, em `/opt/agroedge/plataforma`)

O `.env` tem `COMPOSE_FILE=docker-compose.prod.yml`, então o `docker compose` já usa a produção:

```bash
docker compose ps                      # estado
docker compose logs -f --tail=100 app  # logs do app (ou caddy, mosquitto, backup)
docker compose restart app
cat VERSAO                             # commit que está no ar
```

## Backup

Fica em `/opt/agroedge/plataforma/backups/`: um arquivo `agroedge-AAAAMMDD-HHMM.db.gz` por dia,
guardados por 14 dias. Para ter uma cópia fora da VPS, baixe de vez em quando pelo notebook:

```bash
scp "agroedge-vps:/opt/agroedge/plataforma/backups/*.gz" ./backups-vps/
```

Para restaurar:

1. Pare o app: `docker compose stop app`.
2. Descompacte o backup sobre o banco, entrando no volume pelo contêiner de backup:

   ```bash
   docker compose run --rm --entrypoint sh backup -c \
     'gunzip -c /backups/ARQUIVO.db.gz > /data/agroedge.db && rm -f /data/agroedge.db-wal /data/agroedge.db-shm'
   ```

3. Suba de novo: `docker compose start app`.

## Segurança: o que está ativo

- **Servidor:**
  - firewall: o ufw nega tudo, menos as portas 22 (com limite de conexões), 80, 443 e 8883;
  - fail2ban no SSH;
  - SSH só por chave;
  - atualizações de segurança automáticas;
  - Docker com limite no tamanho dos logs.
- **Web:**
  - HTTPS com HSTS e cabeçalhos contra embutir o painel em outro site e contra adivinhação de
    tipo de arquivo;
  - o app em `AMBIENTE=producao` não sobe com segredo fraco;
  - o cookie só trafega por HTTPS;
  - o login tem limite de tentativas;
  - `/api/docs` exige login.
- **Broker:**
  - TLS 1.2 ou mais novo;
  - sem acesso anônimo;
  - senha por placa;
  - a ACL deixa cada placa só nos próprios tópicos;
  - limites de pacote, de conexões e de mensagens na fila.
