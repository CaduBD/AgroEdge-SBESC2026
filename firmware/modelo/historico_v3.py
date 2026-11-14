# AgroEdge - memória e entradas do classificador v3.1 (45 entradas, várias culturas).
# Faz na placa as MESMAS contas da classe PlacaGeral do modelo/06_gerar_dataset_geral.py (e do
# 12, que acrescenta a situação do local), para a placa ver os dados como a rede viu no treino.
# O script modelo/16_conferir_firmware_v3_1.py confere isso no PC.
#
# Diferenças para o historico.py (v1, só uva):
#   - vale para qualquer cultura da biblioteca: usa a fração do ciclo (dia ÷ duração do ciclo)
#     no lugar do DAP da uva, e o p da cultura entra como entrada;
#   - as somas "desde o início" contam a partir de quando a placa começou a ser usada neste
#     ciclo (dias_uso), não desde a poda, porque a placa pode ser instalada no meio do ciclo;
#   - a placa calcula o próprio balanço hídrico com o que sabe (TAW informado, irrigação
#     informada) e ele entra como entrada: a rede aprende a corrigi-lo;
#   - 8 entradas de situação: de onde vem a irrigação (config_local.FONTE_IRRIGACAO) e como a
#     placa foi instalada (config_local.INICIO_USO).
#
# Uso, uma vez por dia, no fim do dia:
#   h = historico_v3.HistoricoV3()                 # carrega o arquivo, se existir
#   x, deficit = h.fechar_dia(dap, eto, chuva, irrigacao, tmax, tmin, ur, vento, radiacao)
#   classe, saidas = classificador.classificar(x, agroedge_pesos_v3_1)
#   h.salvar()

import json

try:
    import config_local as cfg
except ImportError:
    cfg = None

VERSAO = "v3_1"
JANELAS = (3, 7, 14, 28)
LIMITE_DIAS = 60          # dias_uso e dias_sem_irrigar saturam aqui (como no treino)
FONTES = ("sensor", "manual", "tempo", "parcial", "nenhuma")
INICIOS = ("ciclo", "apos_irr", "meio")


def balanco(dr, etc, chuva, irr, taw, p):
    """FAO-56 eq. 84 e 85 (igual ao lamina.atualizar_deficit). Devolve (déficit novo, Ks)."""
    raw = p * taw
    ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p) * taw))
    d = dr + ks * etc - chuva - irr
    if d < 0.0:
        d = 0.0
    return (d if d < taw else taw), ks


class HistoricoV3:
    VERSAO = VERSAO

    def __init__(self, arquivo="historico_v3.json"):
        self.arquivo = arquivo
        self.zerar()
        if arquivo:
            try:
                with open(arquivo) as f:
                    e = json.load(f)
                self.etc, self.chuva, self.irr = e["etc"], e["chuva"], e["irr"]
                self.uso, self.deficit = e["uso"], e["deficit"]
                self.dias, self.desde_irr = e["dias"], e["desde_irr"]
                self.ultimo_dap, self.inicio_efetivo = e["ultimo_dap"], e["inicio_efetivo"]
            except (OSError, ValueError, KeyError):
                pass                          # primeiro uso ou arquivo estragado: começa do zero

    def zerar(self):
        """Começo do uso (ou de um novo ciclo): solo considerado cheio, sem histórico."""
        self.etc, self.chuva, self.irr = [], [], []
        self.uso = [0.0, 0.0, 0.0]            # ETc, chuva e irrigação desde o início do uso
        self.deficit = 0.0
        self.dias = 0
        self.desde_irr = LIMITE_DIAS
        self.inicio_efetivo = None        # None = usa config_local.INICIO_USO
        self.ultimo_dap = None

    def salvar(self):
        with open(self.arquivo, "w") as f:
            json.dump({"etc": self.etc, "chuva": self.chuva, "irr": self.irr, "uso": self.uso,
                       "deficit": self.deficit, "dias": self.dias, "desde_irr": self.desde_irr,
                       "ultimo_dap": self.ultimo_dap, "inicio_efetivo": self.inicio_efetivo}, f)

    def fechar_dia(self, dap, eto, chuva, irrigacao, tmax, tmin, ur, vento, radiacao,
                   taw=None, p=None, ciclo=None, kc=None, fonte=None, inicio=None):
        """Registra o dia que terminou e devolve (as 45 entradas na ordem do treino, déficit mm).
        dap = dias desde a DATA_REFERENCIA; irrigacao = mm informados hoje. Os parâmetros com
        None vêm do config_local e da culturas.py (os explícitos servem para a conferência no PC).
        Se o dia do ciclo voltou para trás, houve nova poda/floração: começa um ciclo novo, e a
        partir daí a placa conta como instalada no início do ciclo."""
        if self.ultimo_dap is not None and dap < self.ultimo_dap:
            self.zerar()
            self.inicio_efetivo = "ciclo"
        self.ultimo_dap = dap
        if taw is None:
            taw = cfg.taw()
        if p is None:
            p = cfg.P_DEPLECAO
        if ciclo is None:
            import culturas
            ciclo = culturas.cultura(cfg.CULTURA)["ciclo_dias"] + 1   # como no treino
        if kc is None:
            kc = cfg.kc(dap)
        if fonte is None:
            fonte = getattr(cfg, "FONTE_IRRIGACAO", "tempo")
        if inicio is None:
            inicio = self.inicio_efetivo or getattr(cfg, "INICIO_USO", "meio")

        etc = kc * eto
        for lista, v in ((self.etc, etc), (self.chuva, chuva), (self.irr, irrigacao)):
            lista.append(v)
            if len(lista) > JANELAS[-1]:
                lista.pop(0)
        self.uso = [self.uso[0] + etc, self.uso[1] + chuva, self.uso[2] + irrigacao]
        self.desde_irr = 0 if irrigacao > 0 else min(self.desde_irr + 1, LIMITE_DIAS)
        self.dias += 1
        self.deficit, ks = balanco(self.deficit, etc, chuva, irrigacao, taw, p)

        t = taw
        v = {"TAW": t, "p": p, "kc": kc, "frac_ciclo": dap / ciclo,
             "dias_uso": min(self.dias, LIMITE_DIAS), "ETo": eto, "ETc": etc, "chuva": chuva,
             "irrigacao": irrigacao, "Tmax": tmax, "Tmin": tmin, "UR": ur, "vento": vento,
             "radiacao": radiacao, "dias_sem_irrigar": self.desde_irr}
        for n in JANELAS:
            e, c, i = sum(self.etc[-n:]), sum(self.chuva[-n:]), sum(self.irr[-n:])
            v["ETc_%dd_taw" % n] = e / t
            v["chuva_%dd_taw" % n] = c / t
            v["irrigacao_%dd_taw" % n] = i / t
            if n >= 7:
                v["saldo_%dd_taw" % n] = (c + i - e) / t
        e, c, i = self.uso
        v["ETc_uso_taw"], v["chuva_uso_taw"], v["irrigacao_uso_taw"] = e / t, c / t, i / t
        v["saldo_uso_taw"] = (c + i - e) / t
        v["deficit_placa_taw"] = self.deficit / t
        v["deficit_placa_raw"] = self.deficit / (p * t)
        v["ks_placa"] = ks
        for f in FONTES:
            v["irr_" + f] = 1 if fonte == f else 0
        for s in INICIOS:
            v["inicio_" + s] = 1 if inicio == s else 0
        import agroedge_pesos_v3_1 as P
        return [v[nome] for nome in P.FEATURES], self.deficit
