# AgroEdge - programa principal da estação (BitDogLab / RP2040, MicroPython).
# Lê os sensores o dia todo, fecha o dia à meia-noite (hora local) e, com os totais do dia:
#   ET0 (Penman-Monteith FAO-56) -> ETc = Kc × ET0 -> balanço/histórico -> classificador
#   -> lâmina de irrigação para o dia seguinte. Mostra tudo no display e grava em diario.csv.
#
# Sensores e pinos (todos no config_local.py):
#   DHT22 (T e UR) ............ GPIO18
#   piranômetro RS-485 ........ UART1 GPIO8/9, DE/RE GPIO4 (MAX485)
#   anemômetro Met One 014A ... GPIO17
#   pluviômetro de báscula .... GPIO16
#   relógio DS3231 ............ I²C0 GPIO0/1 (opcional; ou NTP pelo Wi-Fi)
#   display OLED .............. I²C1 GPIO14/15 (o da própria BitDogLab)
#
# Arquivos copiados para a placa: main.py, config_local.py, culturas.py, eto.py, termohigro.py, relogio.py,
# anemometro.py, pluviometro.py, piranometro.py, historico.py, lamina.py, classificador.py,
# agroedge_pesos.py e ssd1306.py.
#
# Irrigação aplicada: o sistema não mede a água que o produtor aplicou. Registre pelo Thonny
# (Ctrl+C para parar, depois):  import main; main.registrar_irrigacao(12.5)   # mm líquidos
# e rode main.py de novo. Sem registro, o dia conta como 0 mm (ver IRRIGACAO_MODO).
#
# Para testar sem esperar a meia-noite:  import main; main.rodar(fechar_agora=True)
#
# Modo de teste de 24 h (config_local.MODO_FECHAMENTO = "24h"): o dia fecha 24 horas de
# funcionamento depois de ligar, e não à meia-noite. Instalando às 10h, às 10h do dia seguinte
# sai um dia completo (um ciclo inteiro de sol, Tmax e Tmin). O tempo é contado pelo próprio
# laço, então o fechamento não depende do relógio; o relógio só dá a data para o ET0 e o DAP
# (sem relógio, usa config_local.DATA_INSTALACAO). Se a energia cair, o tempo desligado não
# conta: a janela continua de onde parou quando a placa volta.

import json
import time

import config_local as cfg
import eto

ARQ_ESTADO = "estado.json"
ARQ_DIARIO = "diario.csv"
ARQ_IRRIG = "irrigacao_hoje.json"

TICK_S = 10            # a cada 10 s: vento e display
LEITURA_S = 60         # a cada 60 s: DHT22 e piranômetro
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


def processar_dia(hist, data, ar, rs, u2, chuva, irrigacao, cobertura):
    """Fecha o dia: devolve um dict com tudo o que vai para o display e o diário.
    hist = historico.Historico(). Só atualiza o histórico se o dia tiver dados suficientes."""
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
    if not no_ciclo:
        avisos.append("dia %d do ciclo fora dos dados de Kc da cultura (0-%d): usado o Kc da fase "
                      "mais próxima" % (dap, culturas.cultura(cfg.CULTURA)["ciclo_dias"]))
    x, deficit = hist.fechar_dia(cfg.taw(), dap, et["et0"], chuva, irrigacao, ar["tmax"],
                                 ar["tmin"], ar["ur_media"], et["u2"], et["rs"])
    classe, _ = classificador.classificar(x)
    _, bruta = lamina.recomendar(classe, deficit)
    r.update(cultura=cfg.CULTURA, dap=dap, fase=fase, kc=kc, etc=kc * et["et0"], classe=classe,
             nome_classe=classificador.CLASSES[classe], deficit=deficit, lamina_bruta=bruta,
             minutos=lamina.tempo_min(bruta), aplicar_l_planta=lamina.litros_planta(bruta),
             aplicar_l_total=lamina.litros_total(bruta))
    if len(hist.etc) < 28:
        avisos.append("histórico com %d dias (< 28): classe pouco confiável" % len(hist.etc))
    if cfg.CULTURA != "uva_italia":
        avisos.append("classificador treinado só com uva: classe pouco confiável nesta cultura")
    elif not 0 <= dap <= 108:
        avisos.append("DAP %d fora do treino (0-108): classe pouco confiável" % dap)
    r["avisos"] = avisos
    return r


def proximo_dia(a, m, d):
    dias = (31, 29 if a % 4 == 0 and (a % 100 != 0 or a % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if d < dias[m - 1]:
        return a, m, d + 1
    return (a + 1, 1, 1) if m == 12 else (a, m + 1, 1)


def linha_diario(r):
    campos = ("data", "cultura", "dap", "fase", "kc", "cobertura", "tmax", "tmin", "ur", "u2",
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


class Estacao:
    def __init__(self):
        import relogio
        import termohigro
        import anemometro
        import pluviometro
        import piranometro
        import historico
        self.relogio = relogio
        self.fonte_hora = relogio.iniciar()
        print("relógio:", self.fonte_hora or ("interno" if relogio.valido() else "NÃO ACERTADO"),
              relogio.agora())
        self.display = Display()
        self.ar = _abrir("DHT22", termohigro.Termohigro)
        self.vento = _abrir("anemômetro", anemometro.Anemometro)
        self.chuva = _abrir("pluviômetro", pluviometro.Pluviometro)
        self.sol = _abrir("piranômetro", piranometro.criar_padrao)
        self.hist = historico.Historico()
        self.estado = {"dia": None, "segundos": 0.0, "energia_j": 0.0, "n_sol": 0, "seg_sol": 0.0}
        try:
            with open(ARQ_ESTADO) as f:
                self.estado.update(json.load(f))
        except (OSError, ValueError):
            pass
        if self.estado["dia"] is None and relogio.valido():
            self.estado["dia"] = list(relogio.hoje())
        self.ultimo = {"t": None, "ur": None, "w": None, "v": None}
        self.ultimo_dia = None

    def salvar(self):
        try:
            with open(ARQ_ESTADO, "w") as f:
                json.dump(self.estado, f)
            for s in (self.ar, self.vento, self.chuva):
                if s:
                    s.salvar()
            self.hist.salvar()
        except OSError as e:
            print("erro ao salvar:", e)

    def ler_lento(self, dt):
        """DHT22 e piranômetro (a cada LEITURA_S). dt = segundos desde a última leitura."""
        if self.ar:
            t, ur = self.ar.ler()
            self.ultimo["t"], self.ultimo["ur"] = t, ur
            self.ar.adicionar(t, ur)
        if self.sol:
            w = self.sol.ler_seguro()
            self.ultimo["w"] = w
            if w is not None:
                self.estado["energia_j"] += w * dt
                self.estado["n_sol"] += 1
                self.estado["seg_sol"] += dt

    def ler_vento(self):
        if self.vento:
            _, _, v = self.vento.medir()
            self.vento.adicionar(v, self.vento.ultimo_dt)
            self.ultimo["v"] = v

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
        chuva = self.chuva.fechar_dia() if self.chuva else 0.0
        irr = irrigacao_hoje() if _c("IRRIGACAO_MODO", "arquivo") == "arquivo" else 0.0
        cobertura = min(1.0, e["segundos"] / 86400)
        r = processar_dia(self.hist, data, ar, rs, u2, chuva, irr, cobertura)
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
        _zerar_irrigacao()
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
            self.display.linhas(
                "AgroEdge %02d:%02d" % (a[3], a[4]) if self.relogio.valido() else "AgroEdge SEM HORA",
                "T  " + f(u["t"], "%.1f C") + " UR " + f(u["ur"], "%.0f%%"),
                "Sol " + f(u["w"], "%d W/m2"),
                "Vento " + f(u["v"], "%.1f m/s"),
                "Chuva " + (("%.1f mm" % self.chuva.chuva_mm()) if self.chuva else "--"),
                "Irrig %.1f mm" % irrigacao_hoje())
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

    def rodar(self, fechar_agora=False):
        if self.estado["dia"] is None:
            print("ATENÇÃO: relógio não acertado. Ligue o DS3231 ou o Wi-Fi, ou rode",
                  "relogio.acertar(ano, mes, dia, hora, minuto). Coletando mesmo assim.")
        t_ant = time.ticks_ms()
        t_lento = -LEITURA_S
        t_salvo = 0
        decorrido = 0.0
        pagina = 0
        while True:
            agora = time.ticks_ms()
            dt = time.ticks_diff(agora, t_ant) / 1000
            t_ant = agora
            decorrido += dt
            self.estado["segundos"] += dt
            self.ler_vento()
            if decorrido - t_lento >= LEITURA_S:
                # a primeira leitura não soma energia; as outras somam o tempo real desde a anterior
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
            if decorrido - t_salvo >= SALVAR_S:
                self.salvar()
                t_salvo = decorrido
            pagina = 1 - pagina
            self.mostrar(pagina)
            time.sleep(TICK_S)


def rodar(fechar_agora=False):
    est = Estacao()
    try:
        est.rodar(fechar_agora)
    except KeyboardInterrupt:
        est.salvar()
        print("parado; acumulados salvos")


if __name__ == "__main__":
    try:
        import machine  # noqa: F401
        rodar()
    except ImportError:
        print("main.py roda na placa; no PC use teste_main_pc.py")
