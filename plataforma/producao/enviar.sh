#!/usr/bin/env bash
# Envia a plataforma para a VPS e sobe a produção. Roda no notebook, no Git Bash.
#
#   bash producao/enviar.sh                              # atualiza (o uso do dia a dia)
#   bash producao/enviar.sh --primeira-vez agroedge.tech  # primeira subida num servidor novo
#   bash producao/enviar.sh --so-enviar                  # só copia os arquivos
#
# Envia o que está COMMITADO (git archive do HEAD), não a pasta de trabalho: a VPS roda
# sempre uma versão exata do git. O .env, o mosquitto/passwd e os backups do servidor não
# são tocados. O acesso é pela chave SSH (alias "agroedge-vps" no ~/.ssh/config).
set -euo pipefail

HOST="${AGROEDGE_VPS:-agroedge-vps}"
BASE=/opt/agroedge
PASTA="$BASE/plataforma"

MODO=atualizar
DOMINIO=""
case "${1:-}" in
"") ;;
--so-enviar) MODO=so-enviar ;;
--primeira-vez)
	MODO=primeira-vez
	DOMINIO="${2:?use: --primeira-vez SEU-DOMINIO (ex.: agroedge.tech)}"
	;;
*)
	echo "opção desconhecida: $1" >&2
	exit 2
	;;
esac

RAIZ="$(git rev-parse --show-toplevel)"
cd "$RAIZ"
VERSAO="$(git rev-parse --short HEAD)"
if [ -n "$(git status --porcelain -- plataforma)" ]; then
	echo "aviso: há mudanças não commitadas em plataforma/; vai só o commit $VERSAO"
fi

echo "→ enviando $VERSAO para $HOST:$PASTA"
git archive --format=tar HEAD plataforma | ssh "$HOST" "
	set -e
	command -v rsync >/dev/null || apt-get install -y -qq rsync >/dev/null
	rm -rf $BASE/.novo && mkdir -p $BASE/.novo $PASTA
	tar -x -C $BASE/.novo
	rsync -a --delete \
		--exclude=/.env --exclude=/mosquitto/passwd --exclude=/backups/ --exclude=/VERSAO \
		$BASE/.novo/plataforma/ $PASTA/
	rm -rf $BASE/.novo
	echo $VERSAO > $PASTA/VERSAO
"
[ "$MODO" = so-enviar ] && exit 0

if [ "$MODO" = primeira-vez ]; then
	echo "→ primeira vez: .env com segredos novos (gerados no servidor) e senhas do broker"
	ssh "$HOST" "
		set -e
		cd $PASTA
		python3 backend/scripts/gerar_env.py --producao '$DOMINIO'
		python3 backend/scripts/gerar_passwd.py
	"
fi

echo "→ subindo (o build do painel leva alguns minutos na primeira vez)"
ssh "$HOST" "
	set -e
	cd $PASTA
	test -f .env || { echo 'falta o .env: use --primeira-vez SEU-DOMINIO'; exit 1; }
	docker compose up -d --build --remove-orphans
	docker image prune -f >/dev/null
"

# Uma conexão só (o firewall barra mais de 6 conexões SSH em 30 s).
echo "→ esperando o app (as migrações rodam na partida)"
ssh "$HOST" "cd $PASTA && bash -s -- $MODO" <<'REMOTO'
pronto=0
for _ in $(seq 1 60); do
	if docker compose exec -T app python -c \
		'import urllib.request as u; u.urlopen("http://localhost:8000/api/saude")' >/dev/null 2>&1; then
		pronto=1
		break
	fi
	sleep 3
done
if [ "$pronto" != 1 ]; then
	echo "o app não subiu em 3 min; últimas linhas do log:"
	docker compose logs --tail=30 app
	exit 1
fi
if [ "$1" = primeira-vez ]; then
	docker compose exec -T app python -m scripts.seed
fi
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
REMOTO

DOMINIO="$(ssh "$HOST" "grep '^DOMINIO=' $PASTA/.env | cut -d= -f2")"
echo "→ conferindo https://$DOMINIO/api/saude"
for _ in $(seq 1 30); do
	if curl -fsS --max-time 5 "https://$DOMINIO/api/saude"; then
		echo
		echo "pronto: https://$DOMINIO (versão $VERSAO)"
		exit 0
	fi
	sleep 5
done
echo "o site não respondeu em 2,5 min; veja: ssh $HOST 'cd $PASTA && docker compose logs --tail=50'"
exit 1
