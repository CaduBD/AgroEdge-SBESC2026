#!/usr/bin/env bash
# Liga o chatbot do Telegram na VPS. Roda no notebook, no Git Bash, uma vez (ou para trocar o
# token do bot).
#
#   bash producao/configurar_chatbot.sh
#
# Pede o token do @BotFather sem mostrar na tela e grava só no .env da VPS. O token vai pela
# entrada do SSH, sem aparecer na linha de comando. O bot usa o CHATBOT_TOKEN que já está lá.
#
# Atenção: o mesmo bot do Telegram não pode rodar em dois lugares ao mesmo tempo (o Telegram
# entrega cada mensagem a um só). Para testar no computador, use outro bot, de teste.
set -euo pipefail

HOST="${AGROEDGE_VPS:-agroedge-vps}"
PASTA=/opt/agroedge/plataforma

read -rsp "Token do bot (do @BotFather; não aparece na tela): " TOKEN
echo
if ! [[ "$TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]]; then
	echo "isso não parece um token do Telegram (formato 123456789:ABC...)" >&2
	exit 1
fi

printf '%s\n' "$TOKEN" | ssh "$HOST" "
	set -e
	cd $PASTA
	read -r T
	sed -i '/^TELEGRAM_BOT_TOKEN=/d; /^COMPOSE_PROFILES=/d' .env
	printf '\n# Chatbot do Telegram (configurar_chatbot.sh)\nTELEGRAM_BOT_TOKEN=%s\nCOMPOSE_PROFILES=chatbot\n' \"\$T\" >> .env
	chmod 600 .env
	echo '→ montando e subindo o chatbot'
	docker compose up -d --build chatbot </dev/null 2>&1 | grep -E 'Built|Started|Running|rror' || true
	sleep 8
	docker compose ps chatbot --format '{{.Service}}: {{.Status}}' </dev/null
	docker compose logs --tail=8 chatbot </dev/null
"
echo "pronto. No painel: Conta → Telegram → informe o @ do bot e gere o QR code para conectar."
