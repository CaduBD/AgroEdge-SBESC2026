"""
AgroEdge - dataset do classificador GERAL (v2): várias culturas e dados faltando.

O que muda em relação ao 01_gerar_dataset.py (v1, só uva):

1. Culturas sorteadas. Cada cenário sorteia uma cultura: 70% "sintéticas" (curva de Kc no
   formato do FAO-56, com Kc inicial, médio e final e duração das fases sorteados) e 30%
   reais da biblioteca firmware/modelo/culturas.py (uva Itália e manga Tommy Atkins). Também
   sorteia p, raiz e solo. A rede aprende a regra geral, não uma planta.

2. Verdade × o que a placa vê. O rótulo vem do balanço FAO-56 com os dados VERDADEIROS da
   simulação. As entradas da rede são o que a placa veria no campo:
   - irrigação: o produtor registra tudo, registra só parte (alguns eventos e com erro na
     quantidade) ou nunca registra;
   - ET0 com erro de calibração do cenário (±10%) e ruído diário (5%);
   - chuva medida a menos (o pluviômetro perde parte da chuva: 0 a 30%);
   - TAW informado com erro de ±25% (o tipo de solo quase sempre é estimado);
   - metade dos cenários liga a placa no meio do ciclo (sem o histórico do começo).

3. Entradas que valem para qualquer cultura: em vez do DAP da uva, a fração do ciclo;
   o p da cultura entra como entrada; somas divididas pelo TAW informado; e o balanço que a
   própria placa calcula com os dados que tem (que a rede pode aprender a corrigir).

A comparação honesta (script 07) é a rede contra esse mesmo balanço da placa com limiares,
os dois com os mesmos dados incompletos.

Uso: python3 06_gerar_dataset_geral.py -> dados/dataset_geral.csv
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "firmware", "modelo"))
culturas = import_module("culturas")
CSV_CLIMA = os.path.join(AQUI, "dados", "petrolina_clima_2000_2009.csv")
SAIDA = os.path.join(AQUI, "dados", "dataset_geral.csv")

# ---------------------------------------------------------------- parâmetros
SEMENTE = 7
CENARIOS_POR_ANO = 60
KS_CRITICO = 0.5                     # mesma definição de "crítico" da v1
AGUA_DISP_FAIXA = (0.06, 0.18)       # θCC − θPMP, de arenoso a Vertissolo (FAO-56, tab. 19)
# cultura sintética (faixas largas que contêm uva e manga; FAO-56, tab. 11, 12 e 22)
CICLO_FAIXA = (90, 200)              # dias
KC_INI_FAIXA = (0.30, 0.70)
KC_MID_FAIXA = (0.60, 1.15)
KC_END_FAIXA = (0.40, 1.00)
P_FAIXA = (0.30, 0.65)
ZR_FAIXA = (0.4, 1.2)
PROB_REAL = {"uva_italia": 0.15, "manga_tommy_atkins": 0.15}
ZR_REAL = {"uva_italia": (0.4, 0.8), "manga_tommy_atkins": (0.4, 1.0)}
# modelo de observação (o que a placa vê)
REGISTRO = {"completo": 0.35, "parcial": 0.35, "nunca": 0.30}
ET0_VIES = (0.90, 1.10)
ET0_RUIDO = 0.05
CHUVA_FATOR = (0.70, 1.00)
TAW_ERRO = (0.75, 1.25)
PROB_INICIO_MEIO = 0.5               # placa ligada entre o dia 1 e a metade do ciclo
LIMITE_DIAS = 60                     # dias_uso e dias_sem_irrigar saturam aqui
JANELAS = (3, 7, 14, 28)

CLASSES = {0: "adequado", 1: "deficit_moderado", 2: "deficit_critico"}


# ---------------------------------------------------------------- culturas
def cultura_sintetica(rng):
    """Curva de Kc no formato do FAO-56 (fig. 25): inicial constante, desenvolvimento
    linear até o médio, médio constante, final linear até o Kc final."""
    L = int(rng.integers(*CICLO_FAIXA))
    f_ini, f_dev, f_mid = rng.uniform(0.10, 0.25), rng.uniform(0.15, 0.35), rng.uniform(0.25, 0.45)
    if f_ini + f_dev + f_mid > 0.95:
        s = (f_ini + f_dev + f_mid) / 0.95
        f_ini, f_dev, f_mid = f_ini / s, f_dev / s, f_mid / s
    k_ini = rng.uniform(*KC_INI_FAIXA)
    k_mid = rng.uniform(max(k_ini, KC_MID_FAIXA[0]), KC_MID_FAIXA[1])
    k_end = rng.uniform(KC_END_FAIXA[0], min(k_mid, KC_END_FAIXA[1]))
    a, b, c = f_ini * L, (f_ini + f_dev) * L, (f_ini + f_dev + f_mid) * L

    def kc(d):
        if d < a:
            return k_ini
        if d < b:
            return k_ini + (k_mid - k_ini) * (d - a) / (b - a)
        if d < c:
            return k_mid
        return k_mid + (k_end - k_mid) * min(1.0, (d - c) / max(L - c, 1))
    return dict(nome="sintetica", L=L, kc=kc, p=rng.uniform(*P_FAIXA), zr=rng.uniform(*ZR_FAIXA))


def cultura_real(nome, rng):
    c = culturas.cultura(nome)
    return dict(nome=nome, L=c["ciclo_dias"] + 1, kc=lambda d: culturas.kc_do_dia(nome, d)[0],
                p=c["p"], zr=rng.uniform(*ZR_REAL[nome]))


def sortear_cultura(rng):
    u = rng.random()
    acum = 0.0
    for nome, prob in PROB_REAL.items():
        acum += prob
        if u < acum:
            return cultura_real(nome, rng)
    return cultura_sintetica(rng)


# ---------------------------------------------------------------- produtor e observação
def politica_aleatoria(rng, raw):
    """Igual à v1: bons e maus manejos para cobrir as 3 classes."""
    if rng.random() < 0.5:
        return dict(tipo="gatilho", gatilho=rng.uniform(0.3, 2.4) * raw,
                    fracao=rng.uniform(0.3, 1.1), falha=rng.uniform(0.0, 0.5))
    return dict(tipo="turno_fixo", turno=int(rng.integers(1, 8)),
                lamina_fator=rng.uniform(0.2, 1.2), falha=rng.uniform(0.0, 0.5))


def sortear_observacao(rng, L):
    tipos = list(REGISTRO)
    reg = tipos[int(rng.choice(len(tipos), p=list(REGISTRO.values())))]
    return dict(registro=reg, prob_reg=rng.uniform(0.4, 0.9), erro_reg=(0.7, 1.3),
                et0_vies=rng.uniform(*ET0_VIES), chuva_fator=rng.uniform(*CHUVA_FATOR),
                taw_fator=rng.uniform(*TAW_ERRO),
                inicio=0 if rng.random() >= PROB_INICIO_MEIO else int(rng.integers(1, L // 2)))


def classe_do_deficit(dr, taw, p):
    raw = p * taw
    if dr <= raw:
        return 0
    return 1 if dr <= taw - KS_CRITICO * (1 - p) * taw else 2


def balanco(dr, etc, chuva, irr, taw, p):
    """FAO-56 eq. 84 e 85, igual ao lamina.atualizar_deficit."""
    raw = p * taw
    ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - p) * taw))
    return min(max(dr + ks * etc - chuva - irr, 0.0), taw), ks


# ---------------------------------------------------------------- entradas da placa
class PlacaGeral:
    """O que a placa calcula todo dia com os dados que tem (base do historico v2)."""

    def __init__(self, taw, p, L):
        self.taw, self.p, self.L = taw, p, L
        self.etc, self.chuva, self.irr = [], [], []
        self.ciclo = [0.0, 0.0, 0.0]
        self.deficit = 0.0
        self.dias = 0
        self.desde_irr = LIMITE_DIAS

    def dia(self, d, kc, eto, chuva, irr, tmax, tmin, ur, vento, rad):
        etc = kc * eto
        for lista, v in ((self.etc, etc), (self.chuva, chuva), (self.irr, irr)):
            lista.append(v)
            if len(lista) > max(JANELAS):
                lista.pop(0)
        self.ciclo = [self.ciclo[0] + etc, self.ciclo[1] + chuva, self.ciclo[2] + irr]
        self.desde_irr = 0 if irr > 0 else min(self.desde_irr + 1, LIMITE_DIAS)
        self.dias += 1
        self.deficit, ks = balanco(self.deficit, etc, chuva, irr, self.taw, self.p)
        t = self.taw
        v = dict(TAW=t, p=self.p, kc=kc, frac_ciclo=d / self.L,
                 dias_uso=min(self.dias, LIMITE_DIAS), ETo=eto, ETc=etc, chuva=chuva,
                 irrigacao=irr, Tmax=tmax, Tmin=tmin, UR=ur, vento=vento, radiacao=rad,
                 dias_sem_irrigar=self.desde_irr)
        for n in JANELAS:
            e, c, i = sum(self.etc[-n:]), sum(self.chuva[-n:]), sum(self.irr[-n:])
            v[f"ETc_{n}d_taw"], v[f"chuva_{n}d_taw"], v[f"irrigacao_{n}d_taw"] = e / t, c / t, i / t
            if n >= 7:
                v[f"saldo_{n}d_taw"] = (c + i - e) / t
        e, c, i = self.ciclo
        v.update(ETc_uso_taw=e / t, chuva_uso_taw=c / t, irrigacao_uso_taw=i / t,
                 saldo_uso_taw=(c + i - e) / t, deficit_placa_taw=self.deficit / t,
                 deficit_placa_raw=self.deficit / (self.p * t), ks_placa=ks)
        return v


FEATURES = None   # preenchido em main() a partir das chaves de PlacaGeral.dia


# ---------------------------------------------------------------- simulação
def simular(clima, inicio_data, cult, ad, pol, obs, rng, cid):
    L, p, kcf = cult["L"], cult["p"], cult["kc"]
    taw = 1000 * ad * cult["zr"]
    taw_inf = taw * obs["taw_fator"]
    dias = clima.loc[inicio_data: inicio_data + pd.Timedelta(days=L - 1)]
    placa = PlacaGeral(taw_inf, p, L)
    dr = 0.0
    linhas = []
    for d, (data, c) in enumerate(dias.iterrows()):
        kc = kcf(d)
        etc = kc * c.ETo
        irr = 0.0
        if rng.random() >= pol["falha"]:
            if pol["tipo"] == "gatilho" and dr > pol["gatilho"]:
                irr = pol["fracao"] * dr
            elif pol["tipo"] == "turno_fixo" and d % pol["turno"] == 0:
                irr = pol["lamina_fator"] * etc * pol["turno"]
        dr, _ = balanco(dr, etc, c.Precipitacao, irr, taw, p)          # VERDADE
        classe = classe_do_deficit(dr, taw, p)
        if d < obs["inicio"]:
            continue                                                  # placa ainda desligada
        # o que a placa vê
        if obs["registro"] == "completo":
            irr_inf = irr
        elif obs["registro"] == "parcial":
            irr_inf = irr * rng.uniform(*obs["erro_reg"]) if irr > 0 and rng.random() < obs["prob_reg"] else 0.0
        else:
            irr_inf = 0.0
        eto_obs = c.ETo * obs["et0_vies"] * (1 + rng.normal(0, ET0_RUIDO))
        chuva_obs = c.Precipitacao * obs["chuva_fator"]
        v = placa.dia(d, kc, eto_obs, chuva_obs, irr_inf, c.Tmax, c.Tmin,
                      c.Umidade_Relativa, c.Velocidade_Vento, c.Radiacao_Solar)
        v.update(data=data, cenario=cid, cultura=cult["nome"], registro=obs["registro"],
                 inicio_meio=int(obs["inicio"] > 0), dia_ciclo=d, Dr=dr, TAW_real=taw,
                 classe=classe,
                 classe_balanco_placa=classe_do_deficit(placa.deficit, taw_inf, p))
        linhas.append(v)
    return linhas


def main():
    global FEATURES
    rng = np.random.default_rng(SEMENTE)
    clima = pd.read_csv(CSV_CLIMA, parse_dates=["data"]).set_index("data").sort_index()
    clima = clima.reindex(pd.date_range(clima.index.min(), clima.index.max(), freq="D")).interpolate()
    linhas, cid = [], 0
    for ano in sorted(set(clima.index.year)):
        for _ in range(CENARIOS_POR_ANO):
            cult = sortear_cultura(rng)
            inicio = pd.Timestamp(ano, 1, 1) + pd.Timedelta(days=int(rng.integers(0, 365)))
            if inicio + pd.Timedelta(days=cult["L"] - 1) > clima.index.max():
                continue
            ad = rng.uniform(*AGUA_DISP_FAIXA)
            pol = politica_aleatoria(rng, cult["p"] * 1000 * ad * cult["zr"])
            obs = sortear_observacao(rng, cult["L"])
            linhas += simular(clima, inicio, cult, ad, pol, obs, rng, cid)
            cid += 1
    df = pd.DataFrame(linhas)
    FEATURES = [k for k in linhas[0] if k not in (
        "data", "cenario", "cultura", "registro", "inicio_meio", "dia_ciclo", "Dr", "TAW_real",
        "classe", "classe_balanco_placa")]
    # split pelo ano do início do cenário (um ciclo não fica metade no treino e metade no teste)
    df["ano"] = df.groupby("cenario")["data"].transform("min").dt.year
    df["split"] = np.where(df.ano <= 2006, "treino", np.where(df.ano <= 2008, "validacao", "teste"))
    df.to_csv(SAIDA, index=False, float_format="%.5f")
    print(f"{len(df)} linhas, {cid} cenários, {len(FEATURES)} entradas")
    print(f"TAW real de {df.TAW_real.min():.0f} a {df.TAW_real.max():.0f} mm")
    print(df.groupby("cenario").first().cultura.value_counts().to_string())
    print(pd.crosstab(df.split, df.classe.map(CLASSES), normalize="index").round(3))


if __name__ == "__main__":
    main()
