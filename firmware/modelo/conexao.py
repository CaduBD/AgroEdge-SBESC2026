# AgroEdge - conexão da estação com a plataforma: Wi-Fi + MQTT (com TLS) + buffer.
#
# Contrato MQTT da plataforma (plataforma/README.md e a especificação, seção 7):
#   a placa publica em agroedge/<serial>/telemetria, diario, irrigacao, status e cmd_resp;
#   a plataforma publica a config (retida) em agroedge/<serial>/config e os comandos em .../cmd.
#
# Tudo o que é da rede fica no config_rede.py (fora do git, um por placa):
#   WIFI_SSID, WIFI_SENHA, MQTT_HOST, MQTT_PORTA, MQTT_TLS, MQTT_CA, MQTT_USUARIO (= serial),
#   MQTT_SENHA. Sem MQTT_HOST, a estação roda sozinha, como antes (só display e diario.csv).
#
# Lições da placa de bancada (plataforma/placa_bancada/README.md), todas tratadas aqui:
#   - publicar BYTES: o umqtt.simple mede a mensagem com len(); num texto com acento isso conta
#     caracteres e não bytes, e o JSON chega cortado;
#   - o TLS confere a validade do certificado pelo relógio, que precisa estar em UTC (relogio.py);
#   - erro de certificado é ValueError, não OSError: os dois derrubam a conexão, nunca o programa;
#   - nada aqui pode travar o laço: Wi-Fi e reconexão não bloqueiam, e o connect tem timeout.
#
# Uso (no main.py):
#   c = conexao.Conexao(ao_receber)       # ao_receber(tipo, dados): tipo = "config" ou "cmd"
#   c.servico()                           # a cada volta do laço: reconecta, lê mensagens, ping
#   c.publicar("telemetria", {...})       # sem rede, guarda no buffer (flash) e manda depois

import gc
import json
import time

import config_local as cfg

ARQ_BUFFER = "buffer_mqtt.json"
ARQ_SEQ = "seq_mqtt.json"
LOTE = 10                 # leituras por mensagem ao esvaziar o buffer (contrato: até 50)
BUFFER_MAX = 400          # leituras guardadas sem rede (as mais antigas saem)
PING_S = 30
RECONEXAO_S = 10          # 1ª espera entre tentativas; dobra a cada falha até RECONEXAO_MAX_S
RECONEXAO_MAX_S = 60


def _c(nome, padrao):
    return getattr(cfg, nome, padrao)


def _ler_json(nome, padrao):
    try:
        with open(nome) as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def _gravar_json(nome, dados):
    try:
        with open(nome, "w") as f:
            json.dump(dados, f)
    except OSError as e:
        print("não gravou", nome, e)


def habilitada():
    return bool(_c("MQTT_HOST", ""))


def serial():
    return _c("MQTT_USUARIO", "")


def wifi(esperar=False):
    """Conecta ao Wi-Fi. Sem `esperar`, não bloqueia: dispara a conexão e devolve na hora
    (o laço tenta de novo depois). Bloquear aqui travaria a leitura dos sensores e a válvula."""
    ssid = _c("WIFI_SSID", "")
    if not ssid:
        return False
    try:
        import network
    except ImportError:
        return False
    w = network.WLAN(network.STA_IF)
    if w.isconnected():
        return True
    w.active(True)
    conectando = getattr(network, "STAT_CONNECTING", None)
    if conectando is None or w.status() != conectando:
        w.connect(ssid, _c("WIFI_SENHA", ""))
    if esperar:
        for _ in range(30):          # até ~15 s, só na partida
            if w.isconnected():
                break
            time.sleep_ms(500)
    return w.isconnected()


def rssi():
    try:
        import network
        return network.WLAN(network.STA_IF).status("rssi")
    except Exception:
        return None


class Conexao:
    def __init__(self, ao_receber):
        import relogio
        self.relogio = relogio
        self.ao_receber = ao_receber
        self.tls = _c("MQTT_TLS", False)
        self.cliente = None
        self.ssl_ctx = None
        self.conectado = False
        self.t_reconectar = -RECONEXAO_MAX_S
        self.espera = RECONEXAO_S
        self.t_ping = time.time()
        self.buffer = _ler_json(ARQ_BUFFER, [])        # [[tipo, payload], ...]
        self.seq = _ler_json(ARQ_SEQ, {"telemetria": 0, "diario": 0})

    # ------------------------------------------------------------ estado na flash

    def proximo_seq(self, tipo):
        self.seq[tipo] = self.seq.get(tipo, 0) + 1
        return self.seq[tipo]

    def salvar(self):
        _gravar_json(ARQ_SEQ, self.seq)
        _gravar_json(ARQ_BUFFER, self.buffer)

    # ------------------------------------------------------------ conexão

    def topico(self, tipo):
        return "agroedge/%s/%s" % (serial(), tipo)

    def _contexto_tls(self):
        """Contexto TLS criado uma vez só: confia só na raiz MQTT_CA (Let's Encrypt)."""
        if self.ssl_ctx is None:
            import ssl
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.verify_mode = ssl.CERT_REQUIRED
            with open(_c("MQTT_CA", "isrg_root_x2.der"), "rb") as f:
                ctx.load_verify_locations(cadata=f.read())
            self.ssl_ctx = ctx
        return self.ssl_ctx

    def conectar(self):
        if not wifi():
            return False
        if not self.relogio.valido():
            return False                 # sem hora certa o TLS recusa o certificado
        from umqtt.simple import MQTTClient
        c = None
        try:
            gc.collect()                 # o handshake TLS precisa de ~64 KB livres
            extra = {"ssl": self._contexto_tls()} if self.tls else {}
            c = MQTTClient(serial(), _c("MQTT_HOST", ""),
                           port=_c("MQTT_PORTA", 8883 if self.tls else 1883),
                           user=serial(), password=_c("MQTT_SENHA", ""), keepalive=60, **extra)
            c.set_last_will(self.topico("status"), "offline", retain=True, qos=1)
            c.set_callback(self._mensagem)
            try:
                c.connect(clean_session=False, timeout=15 if self.tls else 5)
            except TypeError:            # umqtt.simple antigo, sem timeout
                c.connect(clean_session=False)
            self.cliente = c
            self.conectado = True
            c.subscribe(self.topico("config"), qos=1)
            c.subscribe(self.topico("cmd"), qos=1)
            c.publish(self.topico("status"), "online", retain=True, qos=1)
            self.t_ping = time.time()
            print("MQTT conectado em", _c("MQTT_HOST", ""), "(TLS)" if self.tls else "")
            return True
        except (OSError, ValueError) as e:   # ValueError: certificado recusado pelo mbedTLS
            print("MQTT não conectou:", e)
            if c is not None and getattr(c, "sock", None):
                try:
                    c.sock.close()
                except Exception:
                    pass
            self.cair()
            return False

    def cair(self):
        self.conectado = False
        if self.cliente:
            try:
                self.cliente.sock.close()
            except Exception:
                pass
        self.cliente = None

    def servico(self):
        """Chamar a cada volta do laço: reconecta (cada vez mais espaçado), lê mensagens que
        chegaram e mantém a conexão viva. Não bloqueia."""
        if not habilitada():
            return
        agora = time.time()
        if not self.conectado and agora - self.t_reconectar >= self.espera:
            self.t_reconectar = agora
            if self.conectar():
                self.espera = RECONEXAO_S
                if self.buffer:
                    self.esvaziar_buffer()
            else:
                self.espera = min(2 * self.espera, RECONEXAO_MAX_S)
        if self.conectado:
            try:
                self.cliente.check_msg()
                if agora - self.t_ping >= PING_S:
                    self.cliente.ping()
                    self.t_ping = agora
            except (OSError, ValueError) as e:
                print("conexão caiu:", e)
                self.cair()

    def desconectar(self):
        if self.conectado:
            try:
                self.cliente.publish(self.topico("status"), "offline", retain=True, qos=1)
                self.cliente.disconnect()
            except OSError:
                pass
        self.cair()

    # ------------------------------------------------------------ mensagens

    def _mensagem(self, topico, msg):
        try:
            dados = json.loads(msg)
        except ValueError:
            print("payload inválido em", topico)
            return
        if topico.endswith(b"/config"):
            self.ao_receber("config", dados)
        elif topico.endswith(b"/cmd"):
            self.ao_receber("cmd", dados)

    def publicar(self, tipo, payload, guardar=True):
        """Publica (QoS 1). Sem rede, guarda no buffer para mandar depois. True se enviou."""
        if not habilitada():
            return False
        if self.conectado:
            try:
                corpo = json.dumps(payload).encode("utf-8")   # bytes (ver o topo do arquivo)
                self.cliente.publish(self.topico(tipo), corpo, qos=1)
                return True
            except (OSError, ValueError) as e:
                print("caiu ao publicar:", e)
                self.cair()
        if guardar:
            self.buffer.append([tipo, payload])
            excesso = sum(1 for t, _ in self.buffer if t == "telemetria") - BUFFER_MAX
            while excesso > 0:            # descarta as leituras mais antigas
                for i, (t, _) in enumerate(self.buffer):
                    if t == "telemetria":
                        self.buffer.pop(i)
                        break
                excesso -= 1
            self.salvar()
        return False

    def leituras_no_buffer(self):
        return sum(1 for t, _ in self.buffer if t == "telemetria")

    def esvaziar_buffer(self):
        """Volta da rede: manda o atrasado do mais antigo para o mais novo, em lotes."""
        leituras = [p for t, p in self.buffer if t == "telemetria"]
        outras = [(t, p) for t, p in self.buffer if t != "telemetria"]
        print("rede de volta: enviando %d leituras atrasadas" % len(leituras))
        enviados = 0
        restantes = len(leituras)
        while enviados < len(leituras):
            lote = leituras[enviados:enviados + LOTE]
            restantes -= len(lote)
            for item in lote:
                item["buf"] = restantes
            if not self.publicar("telemetria", lote, guardar=False):
                break
            enviados += len(lote)
            gc.collect()
        sobrou = [["telemetria", p] for p in leituras[enviados:]]
        for i, (tipo, payload) in enumerate(outras):
            if not self.publicar(tipo, payload, guardar=False):
                sobrou += [[t, p] for t, p in outras[i:]]
                break
        self.buffer = sobrou
        self.salvar()
