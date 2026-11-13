# Configuração da placa de bancada. Copie para config_bancada.py (que fica fora do git)
# ou gere com:  python placa_bancada/preparar.py --host <ip-do-notebook>
# Wi-Fi 2,4 GHz (a Pico W não usa 5 GHz). Vazio = usa o do config_local.py do firmware.
WIFI_SSID = ""
WIFI_SENHA = ""

# Broker MQTT: o IP do notebook na MESMA rede Wi-Fi da placa (ipconfig, "Endereço IPv4")
MQTT_HOST = "192.168.0.10"
MQTT_PORTA = 1883
MQTT_USUARIO = "agroedge-00001"  # = serial da placa
MQTT_SENHA = "troque"  # DISPOSITIVO_SENHA do .env (ou a gerada no make dispositivo)

TELEMETRIA_S = 60  # no campo seria 900 (15 min); na bancada, mais rápido para ver chegar
ACELERADO_DIAS = 7  # quantos dias fecham acelerados antes de passar para a meia-noite
DIA_MINUTOS = 10  # duração de cada dia acelerado
PINO_RELE = 19  # relé da válvula solenoide
