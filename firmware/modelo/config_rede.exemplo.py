# AgroEdge - rede da placa: Wi-Fi e acesso à plataforma. UM ARQUIVO POR PLACA, FORA DO GIT.
# Copie para config_rede.py e preencha, ou gere com:  python firmware/preparar_placa.py
# É o único arquivo que muda quando a placa vai para outro lugar (outro Wi-Fi).

# Wi-Fi 2,4 GHz com internet (o da fazenda ou o roteador 4G do celular; a placa não vê 5 GHz)
WIFI_SSID = "NomeDaRede"
WIFI_SENHA = "senha-do-wifi"

# Plataforma AgroEdge (broker MQTT com TLS na VPS)
MQTT_HOST = "mqtt.agroedge.tech"
MQTT_PORTA = 8883
MQTT_TLS = True
MQTT_CA = "isrg_root_x2.der"   # raiz do certificado (Let's Encrypt), gravada junto na placa
MQTT_USUARIO = "agroedge-00001"   # serial da placa, cadastrado na plataforma
MQTT_SENHA = "senha-da-placa"     # gerada no cadastro (preparar_placa.py busca na VPS)
