"""
AgroEdge - v3.1: a v3 retreinada com a manga Palmer (ano todo) entre as culturas reais.

Igual aos scripts 12 (dataset) e 13 (treino), com duas mudanças:
  - culturas reais: uva Itália, manga Tommy Atkins e manga Palmer (10% cada; 70% sintéticas);
  - ciclo das culturas sintéticas sorteado de 90 a 365 dias (antes 90 a 200), para cobrir
    culturas de ano todo como a Palmer (331 dias).
O relatório mostra o resultado por cultura, com destaque para a Palmer, contra a conta do balanço.

Gera dados/dataset_v3_1.csv (fora do git), versoes/v3_1_palmer/agroedge_pesos_v3_1.py e
resultados_v3_1.md. Não mexe no firmware. Uso: python3 14_v3_1_palmer.py
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, confusion_matrix

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
g = import_module("06_gerar_dataset_geral")
d3 = import_module("12_gerar_dataset_v3")

g.PROB_REAL = {"uva_italia": 0.10, "manga_tommy_atkins": 0.10, "manga_palmer": 0.10}
g.ZR_REAL = {"uva_italia": (0.4, 0.8), "manga_tommy_atkins": (0.4, 1.0), "manga_palmer": (0.4, 1.0)}
g.CICLO_FAIXA = (90, 365)
d3.SAIDA = os.path.join(AQUI, "dados", "dataset_v3_1.csv")
PASTA = os.path.join(AQUI, "versoes", "v3_1_palmer")
NOMES = ["adequado", "moderado", "critico"]
CULTURAS = {"sintetica": "sintéticas", "uva_italia": "uva Itália",
            "manga_tommy_atkins": "manga Tommy Atkins", "manga_palmer": "**manga Palmer (ano todo)**"}


def main():
    d3.main()
    t = import_module("07_treinar_mlp_geral")         # TensorFlow só a partir daqui
    r13 = import_module("13_treinar_v3")
    df = pd.read_csv(d3.SAIDA)
    feats = [c for c in df.columns if c not in d3.NAO_ENTRADA]
    tr, va, te = (df[df.split == s] for s in ("treino", "validacao", "teste"))
    melhor = None
    for oc in (16, 32):
        m, media, desvio, prever = t.treinar(tr, va, feats, oc, 0)
        f1 = f1_score(va.classe, prever(va), average="macro")
        print(f"v3.1, {oc} neurônios: F1 validação {f1:.3f}")
        if melhor is None or f1 > melhor[0] + 0.005:
            melhor = (f1, oc, m, media, desvio, prever)
    _, oc, m, media, desvio, prever = melhor
    os.makedirs(PASTA, exist_ok=True)
    n_par = t.exportar(os.path.join(PASTA, "agroedge_pesos_v3_1.py"), feats, oc, media, desvio, m)

    y = te.classe.values
    p_rede, p_bal = prever(te), te.classe_balanco_placa.values
    # híbrido proposto: conta do balanço com sensor de vazão; rede nas outras fontes
    p_hib = np.where(te.fonte.values == "sensor", p_bal, p_rede)
    pred = {"Balanço + limiares": p_bal, f"Rede v3.1 ({len(feats)}-{oc}-3)": p_rede,
            "Híbrido (balanço com sensor, v3.1 nas outras)": p_hib}
    cab = "| método | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |\n|---|---|---|---|---|---|\n"
    out = ["# Classificador v3.1 (v3 + manga Palmer): teste nos cenários de 2009\n\n",
           f"Dataset: {len(df)} dias, {df.cenario.nunique()} cenários; teste: {len(te)} dias, "
           f"{te.cenario.nunique()} cenários ({te[te.cultura == 'manga_palmer'].cenario.nunique()} de Palmer). "
           "Mesmas falhas de campo da v3 (fonte da irrigação e início do uso sorteados).\n\n## Geral\n\n", cab]
    for nome, p in pred.items():
        out.append(t.linha(nome, t.metricas(y, p)))
    out.append("\n## Por cultura (acurácia; entre parênteses, crítico detectado)\n\n| cultura | dias | "
               + " | ".join(pred) + " |\n|---|---|" + "---|" * len(pred) + "\n")
    for k, rot in CULTURAS.items():
        mask = (te.cultura == k).values
        if mask.sum():
            cel = [f"{t.metricas(y[mask], p[mask])['acc']:.3f} ({t.metricas(y[mask], p[mask])['rec_crit']:.2f})"
                   for p in pred.values()]
            out.append(f"| {rot} | {mask.sum()} | " + " | ".join(cel) + " |\n")
    pal = te.cultura == "manga_palmer"
    out.append("\n## Manga Palmer por fonte da irrigação (acurácia: balanço / rede v3.1)\n\n"
               "| fonte | dias | balanço | rede v3.1 |\n|---|---|---|---|\n")
    for k, rot in r13.FONTES.items():
        mask = (pal & (te.fonte == k)).values
        if mask.sum():
            out.append(f"| {rot} | {mask.sum()} | {(y[mask] == p_bal[mask]).mean():.3f} | "
                       f"{(y[mask] == p_rede[mask]).mean():.3f} |\n")
    out.append("\n## Matriz de confusão da rede v3.1 só na Palmer (linhas = real, colunas = predito)\n\n")
    out.append(pd.DataFrame(confusion_matrix(y[pal.values], p_rede[pal.values], labels=[0, 1, 2]),
                            index=NOMES, columns=NOMES).to_markdown() + "\n")
    out.append(f"\nParâmetros: {n_par} (+{2 * len(feats)} de normalização). Pesos em versoes/v3_1_palmer/.\n")
    texto = "".join(out)
    with open(os.path.join(AQUI, "resultados_v3_1.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
