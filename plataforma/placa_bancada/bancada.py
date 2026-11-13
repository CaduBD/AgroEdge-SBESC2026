# ruff: noqa: UP031, SIM105  -- "%" e try/except de propósito: rodam em qualquer MicroPython
# AgroEdge - placa de bancada: a BitDogLab fala com a plataforma (contrato MQTT, seção 7 da
# especificação) SEM os sensores. As leituras de clima são fictícias (curva de um dia de
# Petrolina); ET0, Kc, classificador e lâmina são os DE VERDADE, do firmware (processar_dia
# do main.py, aqui importado como estacao.py). O relé da válvula (GPIO19) é acionado de verdade.
#
# Serve para testar a Fase 7 (placa real ↔ plataforma) antes dos sensores chegarem:
# Wi-Fi + NTP, MQTT com usuário/senha e LWT, telemetria, buffer quando a rede cai,
# fechamento do dia, config retida vinda da plataforma e comandos da válvula.
#
# Fechamento acelerado: os primeiros ACELERADO_DIAS dias fecham a cada DIA_MINUTOS minutos
# (datas a partir de hoje − ACELERADO_DIAS, para não criar dias no futuro). Depois fecha à
# meia-noite, como no campo.
#
# Arquivos na placa: veja placa_bancada/README.md.
# MicroPython: sem f-strings nem typing, para rodar em qualquer versão.

import gc
import json
import sys
import time

import config_bancada as cb
import config_local as cfg

# No PC, testar_no_pc.py injeta substitutos de machine, network e umqtt antes de importar.
import machine
import network
from umqtt.simple import MQTTClient

NA_PLACA = sys.platform == "rp2"

SERIAL = cb.MQTT_USUARIO
# Wi-Fi: o da config da bancada (fora do git) vale sobre o do config_local do firmware.
# O relogio.py do firmware lê cfg.WIFI_SSID para o NTP, então o valor é copiado para lá.
if getattr(cb, "WIFI_SSID", ""):
    cfg.WIFI_SSID = cb.WIFI_SSID
    cfg.WIFI_SENHA = getattr(cb, "WIFI_SENHA", "")
FUSO_S = int(getattr(cfg, "FUSO_HORAS", -3) * 3600)
# MicroPython de algumas placas conta o tempo desde 2000; o contrato pede Unix (1970).
EPOCH = 946684800 if time.gmtime(0)[0] == 2000 else 0
# O relogio.py do firmware acerta o RTC na HORA LOCAL. No PC (teste), o relógio já é UTC.
RTC_LOCAL = True
TS_MINIMO = 1704067200  # 2024-01-01: antes disso a hora não foi acertada

ARQ_CONFIG = "config_plataforma.json"
ARQ_ESTADO = "bancada_estado.json"
ARQ_BUFFER = "bancada_buffer.json"
LOTE = getattr(cb, "LOTE", 10)  # leituras por mensagem ao esvaziar o buffer (contrato: até 50)
BUFFER_MAX = getattr(cb, "BUFFER_MAX", 400)  # leituras guardadas sem rede (as mais antigas saem)
PING_S = 30
RECONEXAO_S = 10  # primeira espera entre tentativas; dobra a cada falha, até RECONEXAO_MAX_S
RECONEXAO_MAX_S = 60
CONEXAO_TIMEOUT_S = 5  # sem isso, cada tentativa com o broker fora trava a placa ~30 s
AMOSTRAS_DIA = 96  # 15 min


def log(*partes):
    print("[%s]" % SERIAL, *partes)


def ts_utc():
    t = time.time() + EPOCH
    return int(t - FUSO_S) if RTC_LOCAL else int(t)


def hora_valida():
    return ts_utc() >= TS_MINIMO


def data_local(ts):
    t = time.gmtime(ts - EPOCH + FUSO_S)  # gmtime de (UTC − 3 h) = data e hora locais
    return t[0], t[1], t[2], t[3], t[4]


def _dias_da_era(a, m, d):
    """Data civil → nº de dias (algoritmo de Howard Hinnant; só inteiros, igual em todo lugar)."""
    a -= m <= 2
    era = a // 400
    aoe = a - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = aoe * 365 + aoe // 4 - aoe // 100 + doy
    return era * 146097 + doe


def _data_civil(z):
    era = z // 146097
    doe = z - era * 146097
    aoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    a = aoe + era * 400
    doy = doe - (365 * aoe + aoe // 4 - aoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return a + (m <= 2), m, d


def menos_dias(data, n):
    return _data_civil(_dias_da_era(*data) - n)


def mais_um_dia(data):
    return _data_civil(_dias_da_era(*data) + 1)


# ---------------------------------------------------------------- arquivos


def ler_json(nome, padrao):
    try:
        with open(nome) as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def gravar_json(nome, dados):
    try:
        with open(nome, "w") as f:
            json.dump(dados, f)
    except OSError as e:
        log("não gravou", nome, e)


# ---------------------------------------------------------------- clima fictício


class Aleatorio:
    """Gerador simples e reprodutível (o random do MicroPython varia entre versões)."""

    def __init__(self, semente):
        self.x = (semente * 2654435761) & 0xFFFFFFFF or 1

    def __call__(self):
        self.x = (1103515245 * self.x + 12345) & 0x7FFFFFFF
        return self.x / 0x7FFFFFFF


def clima(fracao, dia_semente, amostra):
    """Clima plausível de Petrolina numa fração do dia (0 = meia-noite)."""
    import math

    dia = Aleatorio(dia_semente)
    ruido = Aleatorio(dia_semente * 1000 + amostra)
    hora = 24 * fracao
    offset = dia() * 3 - 1.5
    chuvoso = dia() < 0.08
    nublado = dia() < 0.15
    temp = 28.5 + offset + 6.5 * math.sin(2 * math.pi * (hora - 9) / 24) + (ruido() - 0.5) * 0.6
    ur = 78 - (temp - 22) * 3.4 + (ruido() - 0.5) * 3 + (15 if chuvoso else 0)
    ur = max(15.0, min(98.0, ur))
    sol = max(0.0, math.sin(math.pi * (hora - 6) / 12)) if 6 <= hora <= 18 else 0.0
    rad = 920 * sol * (0.55 if (nublado or chuvoso) else 1.0) * (0.92 + ruido() * 0.08)
    vento = max(0.3, min(4.5, 2.5 + 1.2 * math.sin(2 * math.pi * (hora - 14) / 24)))
    chuva = (0.2 + ruido() * 2.8) if (chuvoso and 14 <= hora <= 17) else 0.0
    return {
        "temp_c": round(temp, 1),
        "ur_pct": round(ur, 1),
        "vento_ms": round(vento, 1),
        "rad_wm2": round(rad, 0),
        "chuva_mm": round(chuva, 1),
    }


def totais_do_dia(dia_semente):
    """Totais de um dia fictício inteiro (96 amostras), no formato do processar_dia."""
    temps, urs, ventos, rs, chuva = [], [], [], 0.0, 0.0
    for i in range(AMOSTRAS_DIA):
        c = clima(i / AMOSTRAS_DIA, dia_semente, i)
        temps.append(c["temp_c"])
        urs.append(c["ur_pct"])
        ventos.append(c["vento_ms"])
        rs += c["rad_wm2"] * 900 / 1e6  # W/m² × 15 min → MJ/m²
        chuva += c["chuva_mm"]
    ar = {
        "tmax": max(temps),
        "tmin": min(temps),
        "ur_media": sum(urs) / len(urs),
        "ur_max": max(urs),
        "ur_min": min(urs),
    }
    return ar, rs, sum(ventos) / len(ventos), round(chuva, 1)


# ---------------------------------------------------------------- placa


class Bancada:
    def __init__(self):
        self.rele = machine.Pin(getattr(cb, "PINO_RELE", 19), machine.Pin.OUT, value=0)
        self.cliente = None
        self.conectado = False
        self.t_reconectar = 0
        self.espera_reconexao = RECONEXAO_S
        self.t_ping = time.time()
        self.config = {}
        est = ler_json(ARQ_ESTADO, {})
        self.seq = est.get("seq", 0)
        self.seq_diario = est.get("seq_diario", 0)
        self.data_virtual = tuple(est["data_virtual"]) if est.get("data_virtual") else None
        self.acelerados = est.get("acelerados", getattr(cb, "ACELERADO_DIAS", 7))
        self.inicio_dia = time.time()  # dia acelerado: começa ao ligar
        self.irrigado_dia_mm = est.get("irrigado_dia_mm", 0.0)
        self.ultima_lamina = est.get("ultima_lamina", 0.0)
        self.ultimo_dia_auto = est.get("ultimo_dia_auto")
        self.executados = est.get("executados", [])
        self.buffer = ler_json(ARQ_BUFFER, [])  # [[tipo, payload], ...]
        self.valvula = None  # dict: id, ts_inicio, fim_ms, origem, cmd_id, fator
        self.t_telemetria = 0
        salva = ler_json(ARQ_CONFIG, None)
        if salva:
            self.aplicar_config(salva, nova=False)

    # ------------------------------------------------------------ estado

    def salvar(self):
        gravar_json(
            ARQ_ESTADO,
            {
                "seq": self.seq,
                "seq_diario": self.seq_diario,
                "data_virtual": self.data_virtual,
                "acelerados": self.acelerados,
                "irrigado_dia_mm": self.irrigado_dia_mm,
                "ultima_lamina": self.ultima_lamina,
                "ultimo_dia_auto": self.ultimo_dia_auto,
                "executados": self.executados[-20:],
            },
        )
        gravar_json(ARQ_BUFFER, self.buffer)

    # ------------------------------------------------------------ rede

    def wifi(self, esperar=False):
        """Conecta ao Wi-Fi. Sem `esperar`, não bloqueia: dispara a conexão e devolve na hora
        (o laço tenta de novo depois). Bloquear aqui travaria a telemetria e o fecho da válvula."""
        w = network.WLAN(network.STA_IF)
        if w.isconnected():
            return True
        w.active(True)
        conectando = getattr(network, "STAT_CONNECTING", None)
        if conectando is None or w.status() != conectando:
            w.connect(cfg.WIFI_SSID, cfg.WIFI_SENHA)
        if esperar:
            for _ in range(30):  # até ~15 s, só na partida
                if w.isconnected():
                    break
                time.sleep_ms(500)
        if w.isconnected():
            log("Wi-Fi conectado", w.ifconfig()[0])
            return True
        return False

    def topico(self, tipo):
        return "agroedge/%s/%s" % (SERIAL, tipo)

    def conectar(self):
        if not self.wifi():
            return False
        try:
            c = MQTTClient(
                SERIAL,
                cb.MQTT_HOST,
                port=getattr(cb, "MQTT_PORTA", 1883),
                user=cb.MQTT_USUARIO,
                password=cb.MQTT_SENHA,
                keepalive=60,
            )
            c.set_last_will(self.topico("status"), "offline", retain=True, qos=1)
            c.set_callback(self.ao_receber)
            try:
                c.connect(clean_session=False, timeout=CONEXAO_TIMEOUT_S)
            except TypeError:  # umqtt.simple antigo, sem timeout
                c.connect(clean_session=False)
            self.cliente = c
            self.conectado = True
            c.subscribe(self.topico("config"), qos=1)
            c.subscribe(self.topico("cmd"), qos=1)
            c.publish(self.topico("status"), "online", retain=True, qos=1)
            self.t_ping = time.time()
            log("MQTT conectado em", cb.MQTT_HOST)
            return True
        except OSError as e:
            log("MQTT não conectou:", e)
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

    def publicar(self, tipo, payload, guardar=True):
        """Publica (QoS 1). Sem rede, guarda no buffer para mandar depois."""
        if self.conectado:
            try:
                # Em BYTES: o umqtt.simple mede a mensagem com len(); num str com acento
                # ("histórico") isso conta caracteres, não bytes, e o JSON chega cortado.
                corpo = json.dumps(payload).encode("utf-8")
                self.cliente.publish(self.topico(tipo), corpo, qos=1)
                return True
            except OSError as e:
                log("caiu ao publicar:", e)
                self.cair()
        if guardar:
            self.buffer.append([tipo, payload])
            excesso = sum(1 for t, _ in self.buffer if t == "telemetria") - BUFFER_MAX
            while excesso > 0:  # descarta as leituras mais antigas
                for i, (t, _) in enumerate(self.buffer):
                    if t == "telemetria":
                        self.buffer.pop(i)
                        break
                excesso -= 1
        return False

    def esvaziar_buffer(self, atual):
        """Volta da rede: primeiro a leitura mais recente, depois o atrasado (antigo → novo)."""
        leituras = [p for t, p in self.buffer if t == "telemetria"]
        outras = [(t, p) for t, p in self.buffer if t != "telemetria"]
        atual["buf"] = len(leituras)
        if not self.publicar("telemetria", atual, guardar=False):
            self.buffer.append(["telemetria", atual])
            return
        log("rede de volta: enviando %d leituras atrasadas" % len(leituras))
        restantes = len(leituras)
        enviados = 0
        while enviados < len(leituras):
            lote = leituras[enviados : enviados + LOTE]
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

    # ------------------------------------------------------------ mensagens recebidas

    def ao_receber(self, topico, msg):
        try:
            dados = json.loads(msg)
        except ValueError:
            log("payload inválido em", topico)
            return
        if topico.endswith(b"/config"):
            self.aplicar_config(dados, nova=True)
        elif topico.endswith(b"/cmd"):
            self.executar(dados)

    def aplicar_config(self, c, nova):
        """Config da plataforma (seção 7.3) → valores do config_local do firmware."""
        if nova and c == self.config:
            return  # a mensagem retida chega de novo a cada inscrição
        trocou_local = c.get("instalacao_id") != self.config.get("instalacao_id")
        self.config = c
        import culturas

        a, m, d = (int(x) for x in c["data_referencia"].split("-"))
        cfg.CULTURA = c["cultura"]
        cfg.DATA_REFERENCIA = (a, m, d)
        cfg.AGUA_DISP = c["agua_disp"]
        cfg.RAIZ_M = c["raiz_m"]
        cfg.EFICIENCIA = c["eficiencia"]
        cfg.AREA_M2 = c["area_m2"]
        cfg.VAZAO_L_H = c["vazao_l_h"]
        cfg.N_PLANTAS = c["n_plantas"]
        cfg.FONTE_IRRIGACAO = c["fonte_irrigacao"]
        cfg.INICIO_USO = c["inicio_uso"]
        # valores derivados (o config_local calcula na importação)
        cfg._c = culturas.cultura(cfg.CULTURA)
        cfg.RAIZ_EFETIVA_M = cfg.RAIZ_M if cfg.RAIZ_M is not None else cfg._c["raiz_m"]
        p_local = getattr(cfg, "P_LOCAL", None)
        cfg.P_DEPLECAO = p_local if p_local is not None else cfg._c["p"]
        # lamina e historico leem o cfg nos valores padrão das funções: reimportar
        for nome in ("lamina", "historico", "estacao"):
            if nome in sys.modules:
                del sys.modules[nome]
        if nova:
            gravar_json(ARQ_CONFIG, c)
            if trocou_local:
                import historico

                h = historico.Historico()
                h.zerar()  # outro local: o classificador começa do zero
                h.salvar()
                log("nova instalação %s: histórico zerado" % c.get("instalacao_id"))
            log(
                "config v%s aplicada: %s, referência %s"
                % (c["cfg_v"], c["cultura"], c["data_referencia"])
            )

    def executar(self, cmd):
        cmd_id = cmd.get("id", "")
        if not cmd_id or cmd_id in self.executados:
            return  # comando repetido (QoS 1 pode entregar duas vezes)
        self.executados.append(cmd_id)
        acao, minutos = cmd.get("acao"), cmd.get("minutos")
        if ts_utc() > cmd.get("valido_ate", 0):
            resultado = "recusado_vencido"
        elif acao == "abrir":
            if not isinstance(minutos, (int, float)) or not 1 <= minutos <= 120:
                resultado = "recusado_invalido"
            elif self.valvula:
                resultado = "recusado_em_andamento"
            else:
                self.abrir(minutos * 60, minutos, "manual", cmd_id)
                resultado = "executado"
        elif acao == "cancelar":
            if self.valvula:
                self.fechar("cancelada")
            resultado = "executado"
        else:
            resultado = "recusado_invalido"
        self.publicar("cmd_resp", {"id": cmd_id, "ts": ts_utc(), "resultado": resultado})
        log("comando %s %s -> %s" % (acao, minutos or "", resultado))
        self.salvar()

    # ------------------------------------------------------------ válvula (relé)

    def abrir(self, segundos_rele, minutos_equivalentes, origem, cmd_id):
        """Liga o relé. No dia acelerado, o tempo de relé é comprimido na mesma proporção."""
        ts = ts_utc()
        sufixo = "auto" if origem == "automatica" else "manual"
        self.valvula = {
            "id": "%d-%s" % (ts, sufixo),
            "ts_inicio": ts,
            "fim_ms": time.ticks_add(time.ticks_ms(), int(segundos_rele * 1000)),
            "origem": origem,
            "cmd_id": cmd_id,
            "fator": minutos_equivalentes / max(segundos_rele / 60, 1e-6),
        }
        self.rele.value(1)
        self.publicar("irrigacao", self.payload_irrigacao(None, None, "iniciada"))
        log("válvula ABERTA (%s), %.1f min" % (origem, minutos_equivalentes))

    def fechar(self, estado):
        v = self.valvula
        self.rele.value(0)
        ts_fim = ts_utc()
        minutos = round((ts_fim - v["ts_inicio"]) / 60 * v["fator"], 1)
        mm = round(minutos / 60 * cfg.VAZAO_L_H / cfg.AREA_M2, 2)
        self.irrigado_dia_mm += mm
        self.publicar("irrigacao", self.payload_irrigacao(ts_fim, (minutos, mm), estado))
        log("válvula fechada (%s): %.1f min, %.2f mm" % (estado, minutos, mm))
        self.valvula = None
        self.salvar()

    def payload_irrigacao(self, ts_fim, minutos_mm, estado):
        v = self.valvula
        return {
            "id": v["id"],
            "ts_inicio": v["ts_inicio"],
            "ts_fim": ts_fim,
            "minutos": minutos_mm[0] if minutos_mm else None,
            "mm": minutos_mm[1] if minutos_mm else None,
            "origem": v["origem"],
            "cmd_id": v["cmd_id"],
            "estado": estado,
        }

    # ------------------------------------------------------------ dia (virtual ou real)

    def acelerado(self):
        return self.acelerados > 0

    def dia_semente(self):
        d = self.data_virtual
        return d[0] * 400 + d[1] * 31 + d[2]

    def fracao_do_dia(self):
        if self.acelerado():
            return min(0.999, (time.time() - self.inicio_dia) / (cb.DIA_MINUTOS * 60))
        _, _, _, h, m = data_local(ts_utc())
        return (h * 60 + m) / 1440

    def telemetria(self):
        self.seq += 1
        amostra = int(self.fracao_do_dia() * AMOSTRAS_DIA)
        leitura = {
            "ts": ts_utc(),
            "seq": self.seq,
            "instalacao_id": self.config.get("instalacao_id"),
            "cfg_v": self.config.get("cfg_v"),
            "rssi": self.rssi(),
            "bat_v": None,  # na USB
            "buf": 0,
        }
        leitura.update(clima(self.fracao_do_dia(), self.dia_semente(), amostra))
        if self.conectado and self.buffer:
            self.esvaziar_buffer(leitura)
        else:
            if not self.conectado:
                leitura["buf"] = sum(1 for t, _ in self.buffer if t == "telemetria") + 1
            self.publicar("telemetria", leitura)
        log(
            "telemetria seq=%d temp=%.1f buf=%d%s"
            % (self.seq, leitura["temp_c"], leitura["buf"], "" if self.conectado else " (sem rede)")
        )

    def rssi(self):
        try:
            return network.WLAN(network.STA_IF).status("rssi")
        except Exception:
            return None

    def deve_fechar(self):
        if self.acelerado():
            return time.time() - self.inicio_dia >= cb.DIA_MINUTOS * 60
        a, m, d, _, _ = data_local(ts_utc())
        return (a, m, d) != self.data_virtual

    def fechar_dia(self):
        import estacao
        import historico

        if not self.config:
            log("sem config da plataforma: dia não fechado (instale a placa num cultivo)")
            self.proximo_dia()
            return
        ar, rs, u2, chuva = totais_do_dia(self.dia_semente())
        hist = historico.Historico()
        r = estacao.processar_dia(
            hist, self.data_virtual, ar, rs, u2, chuva, self.irrigado_dia_mm, 1.0
        )
        hist.salvar()  # o fechar_dia do histórico não grava sozinho
        self.seq_diario += 1
        payload = {
            "ts": ts_utc(),
            "seq": self.seq_diario,
            "instalacao_id": self.config.get("instalacao_id"),
            "cfg_v": self.config.get("cfg_v"),
            "taw": round(cfg.taw(), 1),
        }
        for k, v in r.items():
            if k != "nome_classe":
                payload[k] = round(v, 3) if isinstance(v, float) else v
        payload["avisos"] = list(r.get("avisos", [])) + ["placa de bancada: clima fictício"]
        self.publicar("diario", payload)
        self.ultima_lamina = r.get("lamina_bruta") or 0.0
        log(
            "FECHAMENTO %s: ET0=%s classe=%s lâmina=%s mm"
            % (
                payload["data"],
                payload.get("et0"),
                payload.get("classe"),
                payload.get("lamina_bruta"),
            )
        )
        self.proximo_dia()
        self.irrigacao_automatica_do_dia(r)

    def proximo_dia(self):
        if self.acelerado():
            self.acelerados -= 1
            self.data_virtual = mais_um_dia(self.data_virtual)
            if not self.acelerado():  # acabou o acelerado: segue o calendário real
                a, m, d, _, _ = data_local(ts_utc())
                self.data_virtual = (a, m, d)
                log("fim do modo acelerado: a partir de agora fecha à meia-noite")
        else:
            a, m, d, _, _ = data_local(ts_utc())
            self.data_virtual = (a, m, d)
        self.inicio_dia = time.time()
        self.irrigado_dia_mm = 0.0
        self.salvar()

    def irrigacao_automatica_do_dia(self, r):
        """No acelerado, irriga logo após o fechamento, com o tempo de relé comprimido."""
        minutos = r.get("minutos") or 0
        if not self.acelerado() or self.valvula or minutos <= 0:
            return
        if not self.config.get("irrigacao_automatica", True):
            return
        escala = cb.DIA_MINUTOS / 1440  # 1 dia real → DIA_MINUTOS
        self.abrir(max(5, minutos * 60 * escala), minutos, "automatica", None)

    def irrigacao_automatica_real(self):
        """Fora do acelerado: na hora_irrigacao, se o último fechamento pediu água."""
        if self.acelerado() or self.valvula or self.ultima_lamina <= 0:
            return
        if not self.config.get("irrigacao_automatica", True):
            return
        a, m, d, h, mi = data_local(ts_utc())
        hh, mm_ = (int(x) for x in self.config.get("hora_irrigacao", "05:00").split(":"))
        if self.ultimo_dia_auto != [a, m, d] and (h, mi) >= (hh, mm_):
            self.ultimo_dia_auto = [a, m, d]
            minutos = self.ultima_lamina * cfg.AREA_M2 / cfg.VAZAO_L_H * 60
            self.abrir(minutos * 60, minutos, "automatica", None)

    # ------------------------------------------------------------ laço

    def rodar(self):
        import relogio

        log("iniciando placa de bancada (sem sensores)")
        self.wifi(esperar=True)
        fonte = relogio.iniciar(usar_ntp=True) if NA_PLACA else "pc"
        while not hora_valida():
            log("sem hora válida (NTP): tentando de novo em 10 s")
            time.sleep(10)
            relogio.iniciar(usar_ntp=True)
        log(
            "hora acertada (%s): %04d-%02d-%02d %02d:%02d local" % ((fonte,) + data_local(ts_utc()))
        )
        # Os marcos de tempo do __init__ foram tirados antes do NTP; com o relógio acertado, o
        # pulo de hora faria o primeiro dia acelerado "acabar" na hora. Recomeça a contagem.
        self.inicio_dia = self.t_ping = time.time()
        if self.data_virtual is None:
            hoje = data_local(ts_utc())[:3]
            self.data_virtual = menos_dias(hoje, self.acelerados) if self.acelerado() else hoje
        self.conectar()
        intervalo = getattr(cb, "TELEMETRIA_S", 60)
        log(
            "telemetria a cada %d s; %s"
            % (
                intervalo,
                "%d dias acelerados de %s min (dia virtual %04d-%02d-%02d)"
                % ((self.acelerados, cb.DIA_MINUTOS) + tuple(self.data_virtual))
                if self.acelerado()
                else "fechamento à meia-noite",
            )
        )
        try:
            while True:
                agora = time.time()
                if not self.conectado and agora - self.t_reconectar >= self.espera_reconexao:
                    self.t_reconectar = agora
                    if self.conectar():
                        self.espera_reconexao = RECONEXAO_S
                    else:  # broker fora: tenta cada vez mais espaçado (10, 20, 40, 60 s)
                        self.espera_reconexao = min(2 * self.espera_reconexao, RECONEXAO_MAX_S)
                if self.conectado:
                    try:
                        self.cliente.check_msg()
                        if agora - self.t_ping >= PING_S:
                            self.cliente.ping()
                            self.t_ping = agora
                    except OSError as e:
                        log("conexão caiu:", e)
                        self.cair()
                if self.valvula and time.ticks_diff(time.ticks_ms(), self.valvula["fim_ms"]) >= 0:
                    self.fechar("concluida")
                if agora - self.t_telemetria >= intervalo:
                    self.t_telemetria = agora
                    self.telemetria()
                if self.deve_fechar():
                    self.fechar_dia()
                self.irrigacao_automatica_real()
                gc.collect()
                time.sleep_ms(200)
        except KeyboardInterrupt:
            log("parando")
            if self.valvula:
                self.fechar("interrompida")
            if self.conectado:
                try:
                    self.cliente.publish(self.topico("status"), "offline", retain=True, qos=1)
                    self.cliente.disconnect()
                except OSError:
                    pass
            self.rele.value(0)
            self.salvar()


def rodar():
    Bancada().rodar()
