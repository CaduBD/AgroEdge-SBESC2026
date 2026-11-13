#!/bin/sh
# Entrada do Mosquitto na produção.
#
# 1. Espera o Caddy tirar o certificado de $MQTT_DOMINIO (na primeira subida leva segundos).
# 2. Copia certificado e chave para um volume do Mosquitto, com dono 1883 (o usuário do
#    broker): a chave do Caddy é só do root e o Mosquitto não conseguiria ler.
# 3. Sobe o broker e confere o certificado a cada hora. Quando o Caddy renovar (a cada
#    ~60 dias), encerra o broker; o Docker (restart: unless-stopped) sobe de novo já com o
#    certificado novo. As placas reconectam sozinhas e a sessão persistente não perde nada.
set -u

ORIGEM=/caddy/caddy/certificates
DESTINO=/mosquitto/certs
CONF=/producao/mosquitto.conf
CONFERIR_S=${CERT_CONFERIR_S:-3600} # de quanto em quanto tempo olha se o Caddy renovou

achar() { # $1 = crt | key
	find "$ORIGEM" -path "*/$MQTT_DOMINIO/$MQTT_DOMINIO.$1" 2>/dev/null | head -n 1
}

impressao() {
	sha256sum "$(achar crt)" | cut -d " " -f 1
}

echo "aguardando o certificado de $MQTT_DOMINIO (tirado pelo Caddy)..."
while [ -z "$(achar crt)" ] || [ -z "$(achar key)" ]; do
	sleep 5
done

mkdir -p "$DESTINO"
cp "$(achar crt)" "$DESTINO/cert.pem"
cp "$(achar key)" "$DESTINO/key.pem"
chown -R 1883:1883 "$DESTINO"
chmod 0644 "$DESTINO/cert.pem"
chmod 0600 "$DESTINO/key.pem"
atual=$(impressao)
echo "certificado copiado; subindo o broker"

mosquitto -c "$CONF" &
PID=$!
trap 'kill -TERM "$PID" 2>/dev/null; wait "$PID"; exit 0' TERM INT
# Placa nova (criar_dispositivo.py manda SIGHUP ao contêiner): repassa ao broker, que relê
# o passwd e a acl sem derrubar ninguém.
trap 'kill -HUP "$PID" 2>/dev/null' HUP

while kill -0 "$PID" 2>/dev/null; do
	sleep "$CONFERIR_S" &
	wait $!
	if [ "$(impressao)" != "$atual" ]; then
		echo "certificado renovado pelo Caddy: reiniciando o broker para usar o novo"
		kill -TERM "$PID"
		wait "$PID"
		exit 0
	fi
done

wait "$PID"
exit 1
