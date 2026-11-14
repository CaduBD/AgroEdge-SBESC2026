"""
AgroEdge - confere no PC o caminho do firmware com o classificador v3.1
(historico_v3.py -> classificador.py com agroedge_pesos_v3_1.py).

Gera cenários com a mesma simulação do treino (scripts 06 e 12: culturas sintéticas, uva, manga
Tommy Atkins e manga Palmer; todas as fontes de irrigação e formas de instalação), passa cada dia
pelo historico_v3.py como a placa faria e confere:
  1. se as 45 entradas montadas na placa são iguais às do dataset de treino;
  2. se o classificador.py da placa dá a mesma classe que a conta da rede em numpy;
  3. a acurácia nesses cenários (com informação de irrigação), para comparar com o script 15.
Só precisa de numpy e pandas. Uso: python3 16_conferir_firmware_v3_1.py
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
FW = os.path.join(AQUI, "..", "firmware", "modelo")
sys.path.insert(0, FW)
g = import_module("06_gerar_dataset_geral")
d3 = import_module("12_gerar_dataset_v3")
hv3 = import_module("historico_v3")
clf = import_module("classificador")
P = import_module("agroedge_pesos_v3_1")

N_CENARIOS = 120
SEMENTE = 2024
g.PROB_REAL = {"uva_italia": 0.25, "manga_tommy_atkins": 0.25, "manga_palmer": 0.25}
g.ZR_REAL = {"uva_italia": (0.4, 0.8), "manga_tommy_atkins": (0.4, 1.0), "manga_palmer": (0.4, 1.0)}
g.CICLO_FAIXA = (90, 365)


def rede_numpy(x):
    n, h, c = P.N_FEATURES, P.N_OCULTA, P.N_CLASSES
    z = (np.asarray(x, dtype=np.float32) - np.asarray(P.MEDIA)) / np.asarray(P.DESVIO)
    a = np.maximum(0, z @ np.asarray(P.W1).reshape(n, h) + np.asarray(P.B1))
    return (a @ np.asarray(P.W2).reshape(h, c) + np.asarray(P.B2)).argmax(-1)


def main():
    rng = np.random.default_rng(SEMENTE)
    clima = pd.read_csv(g.CSV_CLIMA, parse_dates=["data"]).set_index("data").sort_index()
    clima = clima.reindex(pd.date_range(clima.index.min(), clima.index.max(), freq="D")).interpolate()
    maior = np.zeros(len(P.FEATURES))
    total = iguais = 0
    y_all, p_all, info_all = [], [], []
    feito = 0
    while feito < N_CENARIOS:
        cult = g.sortear_cultura(rng)
        inicio = pd.Timestamp(2006, 1, 1) + pd.Timedelta(days=int(rng.integers(0, 3 * 365)))
        if inicio + pd.Timedelta(days=cult["L"] - 1) > clima.index.max():
            continue
        ad = rng.uniform(*g.AGUA_DISP_FAIXA)
        pol = g.politica_aleatoria(rng, cult["p"] * 1000 * ad * cult["zr"])
        o = d3.observacao(rng, cult["L"])
        linhas = d3.simular(clima, inicio, cult, ad, pol, o, rng, feito)
        feito += 1
        h = hv3.HistoricoV3(arquivo=None)
        for r in linhas:
            x, _ = h.fechar_dia(r["dia_ciclo"], r["ETo"], r["chuva"], r["irrigacao"], r["Tmax"],
                                r["Tmin"], r["UR"], r["vento"], r["radiacao"], taw=r["TAW"],
                                p=r["p"], ciclo=cult["L"], kc=r["kc"], fonte=o["fonte"],
                                inicio=o["inicio_tipo"])
            ref = [r[nome] for nome in P.FEATURES]
            maior = np.maximum(maior, np.abs(np.asarray(x) - np.asarray(ref)))
            c_placa, _ = clf.classificar(x, P)
            iguais += int(c_placa == rede_numpy(ref))
            total += 1
            y_all.append(r["classe"])
            p_all.append(c_placa)
            info_all.append(o["fonte"] in ("sensor", "manual", "tempo"))
    print(f"{N_CENARIOS} cenários, {total} dias")
    print("1. Maior diferença entre as entradas da placa e as do treino:")
    for nome, dif in sorted(zip(P.FEATURES, maior), key=lambda t: -t[1])[:5]:
        print(f"   {nome:22s} {dif:.2e}")
    print(f"   (todas as 45 entradas: maior diferença {maior.max():.2e})")
    print(f"2. classificador.py da placa × rede em numpy: mesma classe em {iguais}/{total} dias "
          f"({100 * iguais / total:.2f}%)")
    y, p, info = np.array(y_all), np.array(p_all), np.array(info_all)
    print(f"3. Acurácia da placa: {100 * (y == p).mean():.1f}% em todos os dias; "
          f"{100 * (y[info] == p[info]).mean():.1f}% com informação de irrigação")
    ok = maior.max() < 1e-6 and iguais / total > 0.999
    print("OK: a placa monta as entradas e classifica como no treino." if ok else "ATENÇÃO: diferença")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
