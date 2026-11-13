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
| `enviar.sh` | Roda no notebook: envia o commit atual para a VPS e sobe |

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
- O certificado é do Let's Encrypt, então a placa valida com a raiz ISRG. Isso fica para a fase
  final da placa (veja `placa_bancada/README.md`, teste de TLS).
- A porta 1883 não fica aberta na internet. A placa de bancada, ainda sem TLS, continua no
  Docker do notebook.

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
