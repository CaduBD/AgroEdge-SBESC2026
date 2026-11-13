#!/bin/sh
# Backup do banco (SQLite) na produção: uma cópia na partida e uma por dia.
#
# Usa o ".backup" do sqlite3, que copia de forma consistente mesmo com o app gravando.
# Guarda em plataforma/backups/ (pasta do servidor, fora do git), compactado, e apaga os
# mais antigos que BACKUP_DIAS. Para ter cópia fora da VPS, baixe pelo notebook
# (veja producao/README.md).
set -u

BANCO=/data/agroedge.db
PASTA=/backups
HORA=${BACKUP_HORA_UTC:-06} # 06h UTC = 03h em Petrolina
MANTER=${BACKUP_DIAS:-14}

if ! command -v sqlite3 >/dev/null 2>&1; then
	apk add --no-cache sqlite >/dev/null || {
		echo "não consegui instalar o sqlite3; tento de novo em 10 min"
		sleep 600
		exit 1
	}
fi

fazer_backup() {
	if [ ! -f "$BANCO" ]; then
		echo "banco ainda não existe ($BANCO); pulando"
		return
	fi
	nome="$PASTA/agroedge-$(date -u +%Y%m%d-%H%M).db"
	if sqlite3 "$BANCO" ".backup '$nome'" && gzip -f "$nome"; then
		echo "backup ok: $(basename "$nome").gz ($(($(wc -c <"$nome.gz") / 1024)) KB)"
	else
		echo "BACKUP FALHOU"
		rm -f "$nome"
	fi
	find "$PASTA" -name 'agroedge-*.db.gz' -mtime +"$MANTER" -delete
}

mkdir -p "$PASTA"
fazer_backup
ultimo_dia=$(date -u +%Y%m%d)
while true; do
	sleep 60
	hoje=$(date -u +%Y%m%d)
	if [ "$(date -u +%H)" = "$HORA" ] && [ "$hoje" != "$ultimo_dia" ]; then
		fazer_backup
		ultimo_dia=$hoje
	fi
done
