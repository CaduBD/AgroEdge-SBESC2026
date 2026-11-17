# AgroEdge - programa principal da estação (BitDogLab / RP2040, MicroPython).
# Lê os sensores o dia todo, fecha o dia à meia-noite (hora local) e, com os totais do dia:
#   ET0 (Penman-Monteith FAO-56) -> ETc = Kc × ET0 -> balanço/histórico -> classificador
#   -> lâmina de irrigação para o dia seguinte. Mostra tudo no display e grava em diario.csv.
#
# Sensores e pinos (todos no config_local.py):
#   AM2302 (T e UR) ........... GPIO17
#   piranômetro RS-485 ........ UART1 GPIO8/9, DE/RE GPIO4 (MAX485)
#   anemômetro Met One 014A ... GPIO18
#   pluviômetro de báscula .... GPIO16
#   relógio DS3231 ............ I²C0 GPIO0/1 (opcional; ou NTP pelo Wi-Fi)
#   display OLED .............. I²C1 GPIO14/15 (o da própria BitDogLab)
#
# Arquivos copiados para a placa: main.py, config_local.py, culturas.py, eto.py, termohigro.py, relogio.py,
# anemometro.py, pluviometro.py, piranometro.py, lamina.py, classificador.py, ssd1306.py e os
# arquivos do classificador escolhido em config_local.MODELO:
#   "v3_1" (padrão): historico_v3.py e agroedge_pesos_v3_1.py
#   "v1": historico.py e agroedge_pesos.py
#
# Classificador v3.1: recebe a situação do local (FONTE_IRRIGACAO, INICIO_USO). Com
# FONTE_IRRIGACAO = "nenhuma" a placa não mostra a classe nem a lâmina (sem saber da irrigação,
# nenhum método acerta; ver modelo/DECISOES.md, seções 14 e 15) e pede o registro da irrigação.
#
# Irrigação aplicada: o sistema não mede a água que o produtor aplicou. Registre pelo Thonny
# (Ctrl+C para parar, depois):  import main; main.registrar_irrigacao(12.5)   # mm líquidos
# e rode main.py de novo. Sem registro, o dia conta como 0 mm (ver IRRIGACAO_MODO).
#
# Para testar sem esperar a meia-noite:  import main; main.rodar(fechar_agora=True)
#
# Plataforma (https://agroedge.tech) por MQTT com TLS, quando o config_rede.py tem MQTT_HOST:
#   - a cada intervalo (15 min por padrão, ajustável no painel) manda a telemetria: médias do
#     intervalo de temperatura, umidade, vento a 2 m e radiação, e a chuva do intervalo;
#   - no fechamento do dia manda o diário (ET0, Kc, classe, lâmina...);
#   - recebe do painel a configuração do cultivo (cultura, data da poda/floração, solo, vazão,
#     irrigação automática...), que vale SOBRE os valores do config_local.py e fica gravada em
#     config_plataforma.json: trocar de cultivo é pelo painel, não pela placa;
#   - recebe os comandos da válvula (abrir X minutos, cancelar) e responde;
#   - irrigação automática na hora configurada, com a lâmina do último fechamento (nunca na
#     indução floral, quando o produtor reduz a água de propósito).
# Sem rede, a estação continua igual: guarda as mensagens e manda quando a rede volta.
# Arquivos da rede: conexao.py, valvula.py, config_rede.py (Wi-Fi e senha; fora do git),
# isrg_root_x2.der (raiz do certificado) e a biblioteca umqtt.simple (mpremote mip install).
#
# Modo de teste de 24 h (config_local.MODO_FECHAMENTO = "24h"): o dia fecha 24 horas de
# funcionamento depois de ligar, e não à meia-noite. Instalando às 10h, às 10h do dia seguinte
# sai um dia completo (um ciclo inteiro de sol, Tmax e Tmin). O tempo é contado pelo próprio
# laço, então o fechamento não depende do relógio; o relógio só dá a data para o ET0 e o DAP
# (sem relógio, usa config_local.DATA_INSTALACAO). Se a energia cair, o tempo desligado não
# conta: a janela continua de onde parou quando a placa volta.

import json
import sys
import time

import config_local as cfg
import eto

ARQ_ESTADO = "estado.json"
ARQ_DIARIO = "diario.csv"
ARQ_IRRIG = "irrigacao_hoje.json"
ARQ_CONFIG_PLATAFORMA = "config_plataforma.json"
ARQ_REDE = "rede_estado.json"
TELEMETRIA_MIN = 15    # padrão até o painel mandar outro intervalo

TICK_S = 10            # a cada 10 s: vento e display
LEITURA_S = 60         # a cada 60 s: AM2302 e piranômetro
SALVAR_S = 600         # a cada 10 min: grava os acumulados na flash
COBERTURA_MIN = 0.8    # fração mínima do dia com leituras para o dia entrar no histórico
VENTO_PADRAO = 2.0     # FAO-56: sem dado de vento, usar 2 m/s


def _c(nome, padrao):
    return getattr(cfg, nome, padrao)


# --------------------------------------------------------------------------------------------
# Parte pura (testável no PC): totais do dia -> ET0, classe e lâmina
# --------------------------------------------------------------------------------------------
def calcular_et0(data, ar, rs, u2):
    """ET0 do dia e de onde veio cada dado. ar = dict do termohigro.fechar_dia().
    Sem T/UR não há ET0. Sem vento usa 2 m/s, sem radiação estima pela amplitude térmica
    (FAO-56, eq. 50, kRs = 0,16 para interior), como o FAO-56 recomenda para dados faltando."""
    avisos = []
    if ar.get("tmax") is None or ar.get("tmin") is None or ar.get("ur_media") is None:
        return None, ["sem temperatura/umidade: ET0 não calculado"]
    j = eto.dia_do_ano(*data)
    lat, alt = _c("LATITUDE", -9.39), _c("ALTITUDE_M", 370)
    if u2 is None:
        u2 = VENTO_PADRAO
        avisos.append("sem vento: usado 2 m/s")
    if rs is None:
        rs = 0.16 * (ar["tmax"] - ar["tmin"]) ** 0.5 * eto.radiacao_extraterrestre(lat, j)
        avisos.append("sem radiação: Rs estimada pela temperatura")
    if ar.get("ur_max") is not None and ar.get("ur_min") is not None:
        valor = eto.penman_monteith(ar["tmax"], ar["tmin"], rs, u2, j, lat, alt,
                                    ur_max=ar["ur_max"], ur_min=ar["ur_min"])
    else:
        valor = eto.penman_monteith(ar["tmax"], ar["tmin"], rs, u2, j, lat, alt,
                                    ur_media=ar["ur_media"])
    return {"et0": valor, "rs": rs, "u2": u2}, avisos


def novo_historico(arquivo=True):
    """Histórico do classificador escolhido em config_local.MODELO (arquivo=None: só memória)."""
    if _c("MODELO", "v1") == "v3_1":
        import historico_v3
        return historico_v3.HistoricoV3() if arquivo is True else historico_v3.HistoricoV3(arquivo)
    import historico
    return historico.Historico() if arquivo is True else historico.Historico(arquivo)


def processar_dia(hist, data, ar, rs, u2, chuva, irrigacao, cobertura):
    """Fecha o dia: devolve um dict com tudo o que vai para o display e o diário.
    hist = novo_historico() (v1: historico.Historico; v3.1: historico_v3.HistoricoV3).
    Só atualiza o histórico se o dia tiver dados suficientes."""
    import classificador
    import lamina
    r = {"data": "%04d-%02d-%02d" % data, "chuva": chuva, "irrigacao": irrigacao,
         "tmax": ar.get("tmax"), "tmin": ar.get("tmin"), "ur": ar.get("ur_media"),
         "cobertura": cobertura, "et0": None, "etc": None, "classe": None, "deficit": None,
         "lamina_bruta": None, "minutos": None, "consumo_l_planta": None, "consumo_l_total": None,
         "aplicar_l_planta": None, "aplicar_l_total": None}
    et, avisos = calcular_et0(data, ar, rs, u2)
    if et:
        r.update(et0=et["et0"], rs=et["rs"], u2=et["u2"])
        # consumo do dia em litros: ETc (mm) × área. Calculado mesmo em dia incompleto ou fora
        # do histórico, porque não depende do classificador
        kc_dia = cfg.kc(cfg.dap(data))
        etc_mm = kc_dia * et["et0"]
        r.update(etc=etc_mm, consumo_l_planta=lamina.litros_planta(etc_mm),
                 consumo_l_total=lamina.litros_total(etc_mm))
    if cobertura < COBERTURA_MIN:
        avisos.append("dia incompleto (%.0f%% com leituras): fora do histórico" % (100 * cobertura))
    if et is None or cobertura < COBERTURA_MIN:
        r["avisos"] = avisos
        return r
    import culturas
    dap = cfg.dap(data)
    kc, fase, no_ciclo = culturas.kc_do_dia(cfg.CULTURA, dap)
    manejo = culturas.cultura(cfg.CULTURA).get("manejo", {})
    if fase in manejo:
        avisos.append(manejo[fase])
    if not no_ciclo:
        avisos.append("dia %d do ciclo fora dos dados de Kc da cultura (0-%d): usado o Kc da fase "
                      "mais próxima" % (dap, culturas.cultura(cfg.CULTURA)["ciclo_dias"]))
    if getattr(hist, "VERSAO", "v1") == "v3_1":
        import agroedge_pesos_v3_1
        x, deficit = hist.fechar_dia(dap, et["et0"], chuva, irrigacao, ar["tmax"], ar["tmin"],
                                     ar["ur_media"], et["u2"], et["rs"])
        r.update(modelo="v3_1", cultura=cfg.CULTURA, dap=dap, fase=fase, kc=kc,
                 etc=kc * et["et0"], deficit=deficit)
        if _c("FONTE_IRRIGACAO", "tempo") == "nenhuma":
            avisos.append("sem informação de irrigação: classe e lâmina não calculadas; registre "
                          "a irrigação (painel ou main.registrar_irrigacao) e ajuste "
                          "FONTE_IRRIGACAO")
            r["avisos"] = avisos
            return r
        classe, _ = classificador.classificar(x, agroedge_pesos_v3_1)
    else:
        x, deficit = hist.fechar_dia(cfg.taw(), dap, et["et0"], chuva, irrigacao, ar["tmax"],
                                     ar["tmin"], ar["ur_media"], et["u2"], et["rs"])
        classe, _ = classificador.classificar(x)
        r.update(modelo="v1")
        if len(hist.etc) < 28:
            avisos.append("histórico com %d dias (< 28): classe pouco confiável" % len(hist.etc))
        if cfg.CULTURA != "uva_italia":
            avisos.append("classificador v1 treinado só com uva: classe pouco confiável nesta "
                          "cultura (use MODELO = \"v3_1\")")
        elif not 0 <= dap <= 108:
            avisos.append("DAP %d fora do treino (0-108): classe pouco confiável" % dap)
    _, bruta = lamina.recomendar(classe, deficit)
    r.update(cultura=cfg.CULTURA, dap=dap, fase=fase, kc=kc, etc=kc * et["et0"], classe=classe,
             nome_classe=classificador.CLASSES[classe], deficit=deficit, lamina_bruta=bruta,
             minutos=lamina.tempo_min(bruta), aplicar_l_planta=lamina.litros_planta(bruta),
             aplicar_l_total=lamina.litros_total(bruta))
    r["avisos"] = avisos
    return r


def aplicar_config_plataforma(c):
    """Config do painel (contrato MQTT, seção 7.3) -> valores do config_local, na memória.
    A cultura e os dados do local passam a vir do painel; o config_local fica como padrão."""
    import culturas
    a, m, d = (int(x) for x in c["data_referencia"].split("-"))
    culturas.cultura(c["cultura"])          # erro claro se a placa não conhece a cultura
    cfg.CULTURA = c["cultura"]
    cfg.DATA_REFERENCIA = (a, m, d)
    cfg.AGUA_DISP = c["agua_disp"]
    cfg.RAIZ_M = c.get("raiz_m")
    cfg.EFICIENCIA = c["eficiencia"]
    cfg.AREA_M2 = c["area_m2"]
    cfg.VAZAO_L_H = c["vazao_l_h"]
    cfg.N_PLANTAS = c.get("n_plantas")
    cfg.FONTE_IRRIGACAO = c.get("fonte_irrigacao", "tempo")
    cfg.INICIO_USO = c.get("inicio_uso", "meio")
    # valores derivados (o config_local calcula na importação)
    cfg._c = culturas.cultura(cfg.CULTURA)
    cfg.RAIZ_EFETIVA_M = cfg.RAIZ_M if cfg.RAIZ_M is not None else cfg._c["raiz_m"]
    p_local = getattr(cfg, "P_LOCAL", None)
    cfg.P_DEPLECAO = p_local if p_local is not None else cfg._c["p"]
    # o lamina.py guarda o config nos valores padrão das funções: recarregar no próximo uso
    if "lamina" in sys.modules:
        del sys.modules["lamina"]


def payload_diario(r, taw):
    """Resultado do processar_dia -> mensagem "diario" da plataforma (mesmos nomes)."""
    p = {"taw": round(taw, 1)}
    for k, v in r.items():
        if k not in ("nome_classe", "modelo"):
            p[k] = round(v, 3) if isinstance(v, float) else v
    p["avisos"] = list(r.get("avisos", []))
    return p


def proximo_dia(a, m, d):
    dias = (31, 29 if a % 4 == 0 and (a % 100 != 0 or a % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if d < dias[m - 1]:
        return a, m, d + 1
    return (a + 1, 1, 1) if m == 12 else (a, m + 1, 1)


def linha_diario(r):
    campos = ("data", "modelo", "cultura", "dap", "fase", "kc", "cobertura", "tmax", "tmin", "ur", "u2",
              "rs", "chuva", "irrigacao", "et0", "etc", "consumo_l_planta", "consumo_l_total",
              "deficit", "classe", "lamina_bruta", "aplicar_l_planta", "aplicar_l_total", "minutos")

    def fmt(v):
        if v is None:
            return ""
        return "%.3f" % v if isinstance(v, float) else str(v)
    return ",".join(fmt(r.get(k)) for k in campos) + "," + ";".join(r.get("avisos", [])) + "\n", \
        ",".join(campos) + ",avisos\n"


# --------------------------------------------------------------------------------------------
# Irrigação registrada à mão
# --------------------------------------------------------------------------------------------
def registrar_irrigacao(mm):
    """Soma mm (lâmina líquida que chegou ao solo) na irrigação de hoje."""
    total = irrigacao_hoje() + mm
    with open(ARQ_IRRIG, "w") as f:
        json.dump({"mm": total}, f)
    print("irrigação de hoje: %.1f mm" % total)


def irrigacao_hoje():
    try:
        with open(ARQ_IRRIG) as f:
            return float(json.load(f)["mm"])
    except (OSError, ValueError, KeyError):
        return 0.0


def _zerar_irrigacao():
    try:
        with open(ARQ_IRRIG, "w") as f:
            json.dump({"mm": 0.0}, f)
    except OSError:
        pass


# --------------------------------------------------------------------------------------------
# Parte da placa
# --------------------------------------------------------------------------------------------
class Display:
    def __init__(self):
        self.oled = None
        try:
            from machine import I2C, Pin
            import ssd1306
            i2c = I2C(1, sda=Pin(14), scl=Pin(15), freq=400000)
            if 0x3C in i2c.scan():
                self.oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        except Exception as e:
            print("display indisponível:", e)

    def linhas(self, *txt):
        if self.oled is None:
            return
        try:
            self.oled.fill(0)
            for i, t in enumerate(txt[:6]):
                self.oled.text(t[:16], 0, i * 10 + (2 if i else 0))
            self.oled.show()
        except Exception:
            pass


def _abrir(nome, construtor):
    try:
        return construtor()
    except Exception as e:
        print("%s indisponível: %s" % (nome, e))
        return None


def _ler_json(nome, padrao=None):
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


LACO_MS = 250          # o laço roda a cada 250 ms: rede, comandos e válvula sem atraso
AUTO_MAX_MIN = 480     # irrigação automática: no máximo 8 h seguidas (turno longo da manga)


class Estacao:
    def __init__(self):
        import relogio
        import termohigro
        import anemometro
        import pluviometro
        import piranometro
        import conexao
        import valvula
        self.relogio = relogio
        self.anemometro = anemometro
        self.conexao = conexao
        # Wi-Fi primeiro: o relógio acerta pela internet (NTP) e o TLS precisa da hora certa
        if conexao.habilitada():
            print("Wi-Fi:", "conectado" if conexao.wifi(esperar=True) else
                  "sem conexão (a placa segue medindo e tenta de novo)")
        self.fonte_hora = relogio.iniciar()
        print("relógio:", self.fonte_hora or ("interno" if relogio.valido() else "NÃO ACERTADO"),
              relogio.agora())
        self.display = Display()
        self.ar = _abrir("AM2302", termohigro.Termohigro)
        self.vento = _abrir("anemômetro", anemometro.Anemometro)
        self.chuva = _abrir("pluviômetro", pluviometro.Pluviometro)
        self.sol = _abrir("piranômetro", piranometro.criar_padrao)
        # configuração do cultivo vinda do painel (vale sobre o config_local)
        self.plataforma = {}
        salva = _ler_json(ARQ_CONFIG_PLATAFORMA)
        if salva:
            try:
                aplicar_config_plataforma(salva)
                self.plataforma = salva
                print("cultivo do painel: %s desde %s (config v%s)"
                      % (salva["cultura"], salva["data_referencia"], salva.get("cfg_v")))
            except (KeyError, ValueError) as e:
                print("config do painel inválida, usando o config_local:", e)
        self.hist = novo_historico()
        self.estado = {"dia": None, "segundos": 0.0, "energia_j": 0.0, "n_sol": 0, "seg_sol": 0.0}
        self.estado.update(_ler_json(ARQ_ESTADO, {}))
        if self.estado["dia"] is None and relogio.valido():
            self.estado["dia"] = list(relogio.hoje())
        # válvula e o que a irrigação automática precisa lembrar entre reinícios
        self.valvula = valvula.Valvula()
        self.rede = {"auto_min": 0.0, "ultimo_dia_auto": None, "irr_valvula_mm": 0.0,
                     "executados": []}
        self.rede.update(_ler_json(ARQ_REDE, {}))
        self.con = conexao.Conexao(self.receber) if conexao.habilitada() else None
        self.janela = self._nova_janela()
        self.ultimo = {"t": None, "ur": None, "w": None, "v": None}
        self.ultimo_dia = None

    def salvar(self):
        try:
            _gravar_json(ARQ_ESTADO, self.estado)
            for s in (self.ar, self.vento, self.chuva):
                if s:
                    s.salvar()
            self.hist.salvar()
            self.salvar_rede()
        except OSError as e:
            print("erro ao salvar:", e)

    def salvar_rede(self):
        self.rede["executados"] = self.rede["executados"][-20:]
        _gravar_json(ARQ_REDE, self.rede)
        if self.con:
            self.con.salvar()

    # ------------------------------------------------------------ sensores

    def _nova_janela(self):
        """Somas do intervalo da telemetria (médias e chuva do intervalo)."""
        return {"t": 0.0, "nt": 0, "ur": 0.0, "nur": 0, "w": 0.0, "nw": 0, "v": 0.0, "tv": 0.0,
                "chuva0": self.chuva.chuva_mm() if self.chuva else 0.0, "chuva_extra": 0.0}

    def ler_lento(self, dt):
        """AM2302 e piranômetro (a cada LEITURA_S). dt = segundos desde a última leitura."""
        j = self.janela
        if self.ar:
            t, ur = self.ar.ler()
            self.ultimo["t"], self.ultimo["ur"] = t, ur
            self.ar.adicionar(t, ur)
            if t is not None and ur is not None:
                j["t"] += t
                j["nt"] += 1
                j["ur"] += ur
                j["nur"] += 1
        if self.sol:
            w = self.sol.ler_seguro()
            self.ultimo["w"] = w
            if w is not None:
                self.estado["energia_j"] += w * dt
                self.estado["n_sol"] += 1
                self.estado["seg_sol"] += dt
                j["w"] += w
                j["nw"] += 1

    def ler_vento(self):
        if self.vento:
            _, _, v = self.vento.medir()
            dt = self.vento.ultimo_dt
            self.vento.adicionar(v, dt)
            self.ultimo["v"] = v
            self.janela["v"] += self.anemometro.para_2m(v) * dt
            self.janela["tv"] += dt

    # ------------------------------------------------------------ plataforma (MQTT)

    def intervalo_s(self):
        minutos = self.plataforma.get("intervalo_telemetria_min") or _c("TELEMETRIA_MIN",
                                                                         TELEMETRIA_MIN)
        return 60 * minutos

    def telemetria(self):
        if not self.relogio.valido():
            return                       # sem hora, o "ts" seria rejeitado
        j = self.janela
        media = lambda s, n: round(s / n, 2) if n else None
        chuva = None
        if self.chuva:
            chuva = round(self.chuva.chuva_mm() - j["chuva0"] + j["chuva_extra"], 2)
        leitura = {
            "ts": self.relogio.utc(),
            "seq": self.con.proximo_seq("telemetria"),
            "instalacao_id": self.plataforma.get("instalacao_id"),
            "cfg_v": self.plataforma.get("cfg_v"),
            "temp_c": media(j["t"], j["nt"]),
            "ur_pct": media(j["ur"], j["nur"]),
            "vento_ms": round(j["v"] / j["tv"], 2) if j["tv"] > 0 else None,
            "rad_wm2": media(j["w"], j["nw"]),
            "chuva_mm": chuva,
            "rssi": self.conexao.rssi(),
            "bat_v": None,               # na fonte/USB
            "buf": self.con.leituras_no_buffer() + (0 if self.con.conectado else 1),
        }
        enviou = self.con.publicar("telemetria", leitura)
        self.con.salvar()
        self.janela = self._nova_janela()
        print("telemetria seq=%d T=%s UR=%s%s" % (leitura["seq"], leitura["temp_c"],
                                                  leitura["ur_pct"], "" if enviou else " (sem rede)"))

    def receber(self, tipo, dados):
        """Mensagens da plataforma (chamado pelo conexao.servico)."""
        if tipo == "config":
            self.nova_config(dados)
        elif tipo == "cmd":
            self.executar(dados)

    def nova_config(self, c):
        if c == self.plataforma:
            return                       # a config retida chega de novo a cada conexão
        try:
            aplicar_config_plataforma(c)
        except (KeyError, ValueError) as e:
            print("config do painel recusada:", e)
            return
        trocou_local = c.get("instalacao_id") != self.plataforma.get("instalacao_id")
        self.plataforma = c
        _gravar_json(ARQ_CONFIG_PLATAFORMA, c)
        if trocou_local:
            self.hist.zerar()            # outro cultivo: o classificador começa do zero
            self.hist.salvar()
            print("nova instalação %s: histórico zerado" % c.get("instalacao_id"))
        print("config v%s aplicada: %s, referência %s"
              % (c.get("cfg_v"), c["cultura"], c["data_referencia"]))

    def executar(self, cmd):
        cmd_id = cmd.get("id", "")
        if not cmd_id or cmd_id in self.rede["executados"]:
            return                       # repetido (o QoS 1 pode entregar duas vezes)
        self.rede["executados"].append(cmd_id)
        acao, minutos = cmd.get("acao"), cmd.get("minutos")
        if self.relogio.utc() > cmd.get("valido_ate", 0):
            resultado = "recusado_vencido"
        elif acao == "abrir":
            if not isinstance(minutos, (int, float)) or not 1 <= minutos <= 120:
                resultado = "recusado_invalido"
            elif self.valvula.aberta:
                resultado = "recusado_em_andamento"
            else:
                self.abrir_valvula(minutos, "manual", cmd_id)
                resultado = "executado"
        elif acao == "cancelar":
            if self.valvula.aberta:
                self.fechar_valvula("cancelada")
            resultado = "executado"
        else:
            resultado = "recusado_invalido"
        if self.con:
            self.con.publicar("cmd_resp", {"id": cmd_id, "ts": self.relogio.utc(),
                                           "resultado": resultado})
        print("comando %s %s -> %s" % (acao, minutos or "", resultado))
        self.salvar_rede()

    def abrir_valvula(self, minutos, origem, cmd_id):
        p = self.valvula.abrir(minutos, origem, cmd_id, self.relogio.utc())
        if self.con:
            self.con.publicar("irrigacao", p)

    def fechar_valvula(self, estado):
        p, mm = self.valvula.fechar(estado, self.relogio.utc())
        self.rede["irr_valvula_mm"] += mm     # entra na irrigação do dia no fechamento
        if self.con:
            self.con.publicar("irrigacao", p)
        self.salvar_rede()

    def irrigacao_automatica(self):
        """Na hora_irrigacao do painel, abre a válvula pelo tempo do último fechamento."""
        if self.valvula.aberta or self.rede["auto_min"] <= 0 or not self.relogio.valido():
            return
        if not self.plataforma.get("irrigacao_automatica"):
            return
        a = self.relogio.agora()
        hh, mm = (int(x) for x in str(self.plataforma.get("hora_irrigacao", "05:00")).split(":")[:2])
        hoje = list(a[:3])
        if self.rede["ultimo_dia_auto"] != hoje and (a[3], a[4]) >= (hh, mm):
            self.rede["ultimo_dia_auto"] = hoje
            minutos = min(self.rede["auto_min"], AUTO_MAX_MIN)
            self.rede["auto_min"] = 0.0
            self.abrir_valvula(minutos, "automatica", None)
            self.salvar_rede()

    def servico_rede(self):
        """A cada volta do laço: fecha a válvula na hora, rede, mensagens e irrigação."""
        if self.valvula.venceu():
            self.fechar_valvula("concluida")
        if self.con:
            self.con.servico()
        self.irrigacao_automatica()

    # ------------------------------------------------------------ fechamento do dia

    def fechar_dia(self):
        e = self.estado
        if e["dia"] is None:
            print("sem data (relógio não acertado e sem DATA_INSTALACAO): dia não fechado")
            return
        data = tuple(e["dia"])
        ar = self.ar.fechar_dia() if self.ar else {}
        # radiação: integra só o tempo com leitura e completa a falta pela média, se a
        # cobertura do piranômetro for boa; senão, None (o ET0 estima pela temperatura)
        rs = None
        if e["seg_sol"] > 0 and e["seg_sol"] >= COBERTURA_MIN * e["segundos"]:
            rs = e["energia_j"] / 1e6 * (e["segundos"] / e["seg_sol"])
        u2 = self.vento.fechar_dia()[0] if self.vento else None
        if self.chuva:
            # a chuva da janela da telemetria continua contando depois que o dia zera
            self.janela["chuva_extra"] += self.chuva.chuva_mm() - self.janela["chuva0"]
            self.janela["chuva0"] = 0.0
        chuva = self.chuva.fechar_dia() if self.chuva else 0.0
        # irrigação do dia: a da própria válvula + a registrada à mão (main.registrar_irrigacao)
        irr = self.rede["irr_valvula_mm"]
        if _c("IRRIGACAO_MODO", "arquivo") == "arquivo":
            irr += irrigacao_hoje()
        cobertura = min(1.0, e["segundos"] / 86400)
        r = processar_dia(self.hist, data, ar, rs, u2, chuva, irr, cobertura)
        # irrigação automática de amanhã: o tempo que a lâmina pede, menos nas fases em que o
        # produtor reduz a água de propósito (campo "manejo" da cultura, ex.: indução floral)
        import culturas
        if r.get("fase") in culturas.cultura(cfg.CULTURA).get("manejo", {}):
            self.rede["auto_min"] = 0.0
            if self.plataforma.get("irrigacao_automatica"):
                r.setdefault("avisos", []).append("irrigação automática suspensa nesta fase")
        else:
            self.rede["auto_min"] = r.get("minutos") or 0.0
        self.ultimo_dia = r
        linha, cab = linha_diario(r)
        try:
            novo = True
            try:
                open(ARQ_DIARIO).close()
                novo = False
            except OSError:
                pass
            with open(ARQ_DIARIO, "a") as f:
                if novo:
                    f.write(cab)
                f.write(linha)
        except OSError as ex:
            print("erro no diário:", ex)
        if self.con and self.relogio.valido():
            p = payload_diario(r, cfg.taw())
            p.update(ts=self.relogio.utc(), seq=self.con.proximo_seq("diario"),
                     instalacao_id=self.plataforma.get("instalacao_id"),
                     cfg_v=self.plataforma.get("cfg_v"))
            self.con.publicar("diario", p)
        _zerar_irrigacao()
        self.rede["irr_valvula_mm"] = 0.0
        print("DIA FECHADO:", r)
        e.update(segundos=0.0, energia_j=0.0, n_sol=0, seg_sol=0.0)
        if _c("MODO_FECHAMENTO", "meia_noite") == "24h":
            e["dia"] = self._data_janela(proxima=data)
        else:
            e["dia"] = list(self.relogio.hoje()) if self.relogio.valido() else None
        self.salvar()

    def _data_janela(self, proxima=None):
        """Data que identifica a janela de 24 h: a do relógio, se acertado; senão a
        DATA_INSTALACAO do config (e o dia seguinte a cada janela fechada)."""
        if self.relogio.valido():
            return list(self.relogio.hoje())
        if proxima is not None:
            return list(proximo_dia(*proxima))
        base = _c("DATA_INSTALACAO", None)
        return list(base) if base else None

    def mostrar(self, pagina):
        u = self.ultimo
        f = lambda v, fmt: "--" if v is None else fmt % v
        if pagina == 0 or self.ultimo_dia is None:
            a = self.relogio.agora()
            rede = " *" if self.con and self.con.conectado else ""
            self.display.linhas(
                ("AgroEdge %02d:%02d" % (a[3], a[4]) + rede) if self.relogio.valido()
                else "AgroEdge SEM HORA",
                "T  " + f(u["t"], "%.1f C") + " UR " + f(u["ur"], "%.0f%%"),
                "Sol " + f(u["w"], "%d W/m2"),
                "Vento " + f(u["v"], "%.1f m/s"),
                "Chuva " + (("%.1f mm" % self.chuva.chuva_mm()) if self.chuva else "--"),
                ("VALVULA ABERTA" if self.valvula.aberta else "Irrig %.1f mm" % irrigacao_hoje()))
        else:
            r = self.ultimo_dia
            tot = r.get("aplicar_l_total")
            self.display.linhas(
                r["data"][5:] + " ET0 " + f(r.get("et0"), "%.1fmm"),
                "Gasto " + f(r.get("consumo_l_planta"), "%.0f L/pl"),
                (r.get("nome_classe") or "sem classe")[:16],
                "Irrig " + f(r.get("lamina_bruta"), "%.1fmm"),
                "  " + f(r.get("aplicar_l_planta"), "%.0f L/pl") + " " + f(r.get("minutos"), "%.0fm"),
                "Total " + (("%.1f m3" % (tot / 1000)) if tot is not None else "--"))

    # ------------------------------------------------------------ laço

    def rodar(self, fechar_agora=False):
        if self.estado["dia"] is None:
            print("ATENÇÃO: relógio não acertado. Ligue o DS3231 ou o Wi-Fi, ou rode",
                  "relogio.acertar(ano, mes, dia, hora, minuto). Coletando mesmo assim.")
        t_ant = time.ticks_ms()
        t_lento = -LEITURA_S
        t_tick = -TICK_S
        t_salvo = 0
        t_tele = 60 - self.intervalo_s()   # 1ª telemetria 1 min depois de ligar
        decorrido = 0.0
        pagina = 0
        while True:
            agora = time.ticks_ms()
            dt = time.ticks_diff(agora, t_ant) / 1000
            t_ant = agora
            decorrido += dt
            self.estado["segundos"] += dt
            self.servico_rede()
            if decorrido - t_tick >= TICK_S:
                t_tick = decorrido
                self.ler_vento()
                if decorrido - t_lento >= LEITURA_S:
                    # a primeira leitura não soma energia; as outras somam o tempo real
                    self.ler_lento(decorrido - t_lento if t_lento >= 0 else 0)
                    t_lento = decorrido
                if _c("MODO_FECHAMENTO", "meia_noite") == "24h":
                    # modo de teste: fecha após 24 h de funcionamento, com ou sem relógio
                    if self.estado["dia"] is None:
                        self.estado["dia"] = self._data_janela()
                    if self.estado["segundos"] >= 86400 or fechar_agora:
                        fechar_agora = False
                        self.fechar_dia()
                # virada do dia (o relógio local mudou de data) ou fechamento forçado
                elif self.relogio.valido():
                    hoje = list(self.relogio.hoje())
                    if self.estado["dia"] is None:
                        self.estado["dia"] = hoje
                    elif hoje != self.estado["dia"] or fechar_agora:
                        fechar_agora = False
                        self.fechar_dia()
                if self.con and decorrido - t_tele >= self.intervalo_s():
                    t_tele = decorrido
                    self.telemetria()
                if decorrido - t_salvo >= SALVAR_S:
                    self.salvar()
                    t_salvo = decorrido
                pagina = 1 - pagina
                self.mostrar(pagina)
            time.sleep_ms(LACO_MS)

    def parar(self):
        if self.valvula.aberta:
            self.fechar_valvula("interrompida")
        if self.con:
            self.con.desconectar()
        self.salvar()


def rodar(fechar_agora=False):
    est = Estacao()
    try:
        est.rodar(fechar_agora)
    except KeyboardInterrupt:
        est.parar()
        print("parado; acumulados salvos")


if __name__ == "__main__":
    try:
        import machine  # noqa: F401
        rodar()
    except ImportError:
        print("main.py roda na placa; no PC use teste_main_pc.py")
