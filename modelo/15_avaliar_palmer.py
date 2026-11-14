"""
AgroEdge - avaliação da v3.1 só na manga Palmer, com mais cenários.

No 14, o teste (cenários que começam em 2009) quase não tem Palmer: o ciclo dela tem 331 dias e
o clima termina em 31/12/2009, então só 4 ciclos cabiam. Aqui geramos 150 ciclos de Palmer que
começam entre jun/2007 e jan/2009 (anos fora do treino, que vai até 2006; 2007-2008 foram usados
só para escolher o tamanho da rede e parar o treino), com as mesmas falhas de campo sorteadas.
Os pesos são lidos de versoes/v3_1_palmer/ (rode o 14 antes). Só numpy e pandas: não precisa de
TensorFlow. Uso: python3 15_avaliar_palmer.py
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "versoes", "v3_1_palmer"))
g = import_module("06_gerar_dataset_geral")
d3 = import_module("12_gerar_dataset_v3")
P = import_module("agroedge_pesos_v3_1")
N_CICLOS = 150
SEMENTE = 99
FONTES = {"sensor": "sensor de vazão", "manual": "produtor informa a quantidade",
          "tempo": "produtor informa o tempo de válvula", "parcial": "registro de vez em quando",
          "nenhuma": "sem informação"}
INICIOS = {"ciclo": "no início do ciclo", "apos_irr": "no meio, logo após irrigação",
           "meio": "no meio, dia qualquer"}


def rede(x):
    """Inferência da MLP com os pesos exportados (mesma conta do classificador.py)."""
    n, h, c = P.N_FEATURES, P.N_OCULTA, P.N_CLASSES
    z = (x - np.array(P.MEDIA)) / np.array(P.DESVIO)
    a = np.maximum(0, z @ np.array(P.W1).reshape(n, h) + np.array(P.B1))
    return (a @ np.array(P.W2).reshape(h, c) + np.array(P.B2)).argmax(1)


def main():
    g.ZR_REAL["manga_palmer"] = (0.4, 1.0)
    rng = np.random.default_rng(SEMENTE)
    clima = pd.read_csv(g.CSV_CLIMA, parse_dates=["data"]).set_index("data").sort_index()
    clima = clima.reindex(pd.date_range(clima.index.min(), clima.index.max(), freq="D")).interpolate()
    linhas = []
    for cid in range(N_CICLOS):
        cult = g.cultura_real("manga_palmer", rng)
        inicio = pd.Timestamp(2007, 6, 1) + pd.Timedelta(days=int(rng.integers(0, 610)))
        if inicio + pd.Timedelta(days=cult["L"] - 1) > clima.index.max():
            continue
        ad = rng.uniform(*g.AGUA_DISP_FAIXA)
        pol = g.politica_aleatoria(rng, cult["p"] * 1000 * ad * cult["zr"])
        linhas += d3.simular(clima, inicio, cult, ad, pol, d3.observacao(rng, cult["L"]), rng, cid)
    df = pd.DataFrame(linhas)
    y = df.classe.values
    p_rede = rede(df[list(P.FEATURES)].values.astype(np.float64))
    p_bal = df.classe_balanco_placa.values
    p_hib = np.where(df.fonte.values == "sensor", p_bal, p_rede)
    out = [f"# v3.1 na manga Palmer: {df.cenario.nunique()} ciclos, {len(df)} dias (jun/2007 a dez/2009)\n\n",
           "| recorte | dias | balanço | rede v3.1 | híbrido |\n|---|---|---|---|---|\n"]

    def lin(rot, m):
        cr = (y[m] == 2)
        rc = lambda p: (p[m][cr] == 2).mean() if cr.sum() else float("nan")
        out.append(f"| {rot} | {m.sum()} | {(y[m] == p_bal[m]).mean():.3f} ({rc(p_bal):.2f}) | "
                   f"{(y[m] == p_rede[m]).mean():.3f} ({rc(p_rede):.2f}) | "
                   f"{(y[m] == p_hib[m]).mean():.3f} ({rc(p_hib):.2f}) |\n")
    lin("**geral**", np.ones(len(df), bool))
    for k, r in FONTES.items():
        lin(r, (df.fonte == k).values)
    for k, r in INICIOS.items():
        lin(r, (df.inicio_tipo == k).values)
    com_info = df.fonte.isin(["sensor", "manual", "tempo"]).values
    lin("com informação de irrigação (sensor, quantidade ou tempo)", com_info)
    lin("com informação + placa no início ou após irrigação",
        com_info & df.inicio_tipo.isin(["ciclo", "apos_irr"]).values)
    fases = [f[0] for f in import_module("culturas").cultura("manga_palmer")["kc"][1]]
    kcf = import_module("culturas").kc_do_dia
    df["fase"] = [kcf("manga_palmer", d)[1] for d in df.dia_ciclo]
    out.append("\n## Por fase (só com informação de irrigação)\n\n| fase | dias | balanço | rede v3.1 |\n|---|---|---|---|\n")
    for f in fases:
        m = com_info & (df.fase == f).values
        if m.sum():
            out.append(f"| {f} | {m.sum()} | {(y[m] == p_bal[m]).mean():.3f} | {(y[m] == p_rede[m]).mean():.3f} |\n")
    out.append("\nEntre parênteses: fração dos dias críticos detectados.\n")
    texto = "".join(out)
    with open(os.path.join(AQUI, "resultados_v3_1_palmer.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
