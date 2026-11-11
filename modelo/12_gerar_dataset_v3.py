"""
AgroEdge - dataset do classificador v3: UM modelo para todas as situações de campo.

Igual ao 06 (culturas sorteadas, rótulo pelo balanço com os dados verdadeiros, sensores com erro),
mas cada cenário sorteia COMO a irrigação chega à placa e COMO a placa foi instalada, e a rede
recebe essas duas informações como entradas (vêm do config_local / dashboard na instalação).

Fonte da irrigação (entrada one-hot "irr_*"):
  sensor       sensor de vazão/hidrômetro: todas as irrigações, erro de ±5% na quantidade
  manual       produtor informa quanto irrigou (mm ou litros): esquece 2-15%, erra ±25%
  tempo        produtor informa o tempo de válvula; a placa converte pela vazão do config, que
               tem um erro fixo do local (±20%, vazão nominal ≠ real) mais ±5% por evento; esquece 2-10%
  parcial      produtor registra de vez em quando: esquece 10-60%, erra ±25%
  nenhuma      ninguém informa a irrigação

Início do uso (entradas "inicio_*"):
  ciclo        placa ligada no dia da poda/floração
  apos_irr     ligada no meio do ciclo, logo depois de uma irrigação/chuva que encheu o solo
  meio         ligada no meio do ciclo, em um dia qualquer

Uso: python3 12_gerar_dataset_v3.py -> dados/dataset_v3.csv
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
g = import_module("06_gerar_dataset_geral")
SAIDA = os.path.join(AQUI, "dados", "dataset_v3.csv")
SEMENTE = int(os.environ.get("SEMENTE", 13))
CENARIOS_POR_ANO = 120

FONTES = {"sensor": 0.2, "manual": 0.2, "tempo": 0.2, "parcial": 0.2, "nenhuma": 0.2}
INICIOS = {"ciclo": 1 / 3, "apos_irr": 1 / 3, "meio": 1 / 3}
LIMITE_CHEIO = 0.2
CHUVA_GRANDE_MM = 10.0


def sortear(rng, opcoes):
    nomes = list(opcoes)
    return nomes[int(rng.choice(len(nomes), p=list(opcoes.values())))]


def observacao(rng, L):
    fonte, inicio = sortear(rng, FONTES), sortear(rng, INICIOS)
    o = dict(fonte=fonte, inicio_tipo=inicio, et0_vies=rng.uniform(*g.ET0_VIES),
             chuva_fator=rng.uniform(*g.CHUVA_FATOR), taw_fator=rng.uniform(*g.TAW_ERRO),
             inicio=0 if inicio == "ciclo" else int(rng.integers(1, L // 2)))
    if fonte == "sensor":
        o.update(prob_reg=1.0, vies=1.0, erro=0.05)
    elif fonte == "manual":
        o.update(prob_reg=rng.uniform(0.85, 0.98), vies=1.0, erro=0.25)
    elif fonte == "tempo":
        o.update(prob_reg=rng.uniform(0.90, 0.98), vies=rng.uniform(0.8, 1.2), erro=0.05)
    elif fonte == "parcial":
        o.update(prob_reg=rng.uniform(0.40, 0.90), vies=1.0, erro=0.25)
    else:
        o.update(prob_reg=0.0, vies=1.0, erro=0.0)
    return o


def informada(irr, o, rng):
    if irr <= 0 or rng.random() >= o["prob_reg"]:
        return 0.0
    return irr * o["vies"] * rng.uniform(1 - o["erro"], 1 + o["erro"])


def simular(clima, inicio_data, cult, ad, pol, o, rng, cid):
    L, p, kcf = cult["L"], cult["p"], cult["kc"]
    taw = 1000 * ad * cult["zr"]
    taw_inf = taw * o["taw_fator"]
    placa = g.PlacaGeral(taw_inf, p, L)
    dias = clima.loc[inicio_data: inicio_data + pd.Timedelta(days=L - 1)]
    dr, ligada, linhas = 0.0, o["inicio"] == 0, []
    for d, (data, c) in enumerate(dias.iterrows()):
        kc = kcf(d)
        etc = kc * c.ETo
        irr = 0.0
        if rng.random() >= pol["falha"]:
            if pol["tipo"] == "gatilho" and dr > pol["gatilho"]:
                irr = pol["fracao"] * dr
            elif pol["tipo"] == "turno_fixo" and d % pol["turno"] == 0:
                irr = pol["lamina_fator"] * etc * pol["turno"]
        dr, _ = g.balanco(dr, etc, c.Precipitacao, irr, taw, p)            # VERDADE
        classe = g.classe_do_deficit(dr, taw, p)
        if not ligada:
            if d < o["inicio"]:
                continue
            if o["inicio_tipo"] == "apos_irr" and d < L - 1:
                molhou = irr > 0 or c.Precipitacao >= CHUVA_GRANDE_MM
                if not (molhou and dr <= LIMITE_CHEIO * taw):
                    continue
            ligada = True
        v = placa.dia(d, kc, c.ETo * o["et0_vies"] * (1 + rng.normal(0, g.ET0_RUIDO)),
                      c.Precipitacao * o["chuva_fator"], informada(irr, o, rng), c.Tmax, c.Tmin,
                      c.Umidade_Relativa, c.Velocidade_Vento, c.Radiacao_Solar)
        for f in FONTES:
            v["irr_" + f] = int(o["fonte"] == f)
        for i in INICIOS:
            v["inicio_" + i] = int(o["inicio_tipo"] == i)
        v.update(data=data, cenario=cid, cultura=cult["nome"], fonte=o["fonte"],
                 inicio_tipo=o["inicio_tipo"], dia_ciclo=d, Dr=dr, TAW_real=taw, classe=classe,
                 classe_balanco_placa=g.classe_do_deficit(placa.deficit, taw_inf, p))
        linhas.append(v)
    return linhas


INDICADORES = ["irr_" + f for f in FONTES] + ["inicio_" + i for i in INICIOS]
NAO_ENTRADA = ("data", "cenario", "cultura", "fonte", "inicio_tipo", "dia_ciclo", "Dr", "TAW_real",
               "classe", "classe_balanco_placa", "ano", "split")


def main():
    rng = np.random.default_rng(SEMENTE)
    clima = pd.read_csv(g.CSV_CLIMA, parse_dates=["data"]).set_index("data").sort_index()
    clima = clima.reindex(pd.date_range(clima.index.min(), clima.index.max(), freq="D")).interpolate()
    linhas, cid = [], 0
    for ano in sorted(set(clima.index.year)):
        for _ in range(CENARIOS_POR_ANO):
            cult = g.sortear_cultura(rng)
            inicio = pd.Timestamp(ano, 1, 1) + pd.Timedelta(days=int(rng.integers(0, 365)))
            if inicio + pd.Timedelta(days=cult["L"] - 1) > clima.index.max():
                continue
            ad = rng.uniform(*g.AGUA_DISP_FAIXA)
            pol = g.politica_aleatoria(rng, cult["p"] * 1000 * ad * cult["zr"])
            linhas += simular(clima, inicio, cult, ad, pol, observacao(rng, cult["L"]), rng, cid)
            cid += 1
    df = pd.DataFrame(linhas)
    df["ano"] = df.groupby("cenario")["data"].transform("min").dt.year
    df["split"] = np.where(df.ano <= 2006, "treino", np.where(df.ano <= 2008, "validacao", "teste"))
    df.to_csv(SAIDA, index=False, float_format="%.5f")
    print(f"{len(df)} linhas, {cid} cenários, {len([c for c in df.columns if c not in NAO_ENTRADA])} entradas")
    print(df[df.split == "teste"].groupby(["fonte", "inicio_tipo"]).cenario.nunique().unstack())


if __name__ == "__main__":
    main()
