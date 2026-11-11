"""
AgroEdge - treino e teste do classificador v3 (modelo único com entradas de situação).

Compara no teste (cenários de 2009), com os mesmos dados incompletos:
  - balanço da placa + limiares (sem rede);
  - rede SEM as entradas de situação (como a v2: não sabe de onde vem a irrigação);
  - rede v3 COM as entradas de situação (fonte da irrigação e início do uso).
Abre o resultado por fonte da irrigação, por início do uso e pelas 15 combinações.

Grava os pesos em versoes/v3_unico/ e o relatório em resultados_v3.md. Não mexe no firmware.
Uso: python3 13_treinar_v3.py   (depois do 12)
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, confusion_matrix

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
d3 = import_module("12_gerar_dataset_v3")
t = import_module("07_treinar_mlp_geral")
PASTA = os.path.join(AQUI, "versoes", "v3_unico")
NOMES = ["adequado", "moderado", "critico"]
FONTES = {"sensor": "sensor de vazão", "manual": "produtor informa a quantidade",
          "tempo": "produtor informa o tempo de válvula", "parcial": "registro de vez em quando",
          "nenhuma": "sem informação"}
INICIOS = {"ciclo": "no início do ciclo", "apos_irr": "no meio, logo após irrigação",
           "meio": "no meio, dia qualquer"}


def main():
    df = pd.read_csv(d3.SAIDA)
    todas = [c for c in df.columns if c not in d3.NAO_ENTRADA]
    sem_ind = [c for c in todas if c not in d3.INDICADORES]
    tr, va, te = (df[df.split == s] for s in ("treino", "validacao", "teste"))

    modelos = {}
    for nome, feats in (("v3", todas), ("sem_ind", sem_ind)):
        melhor = None
        for oc in ((16, 32, 64) if nome == "v3" else (16, 32)):
            m, media, desvio, prever = t.treinar(tr, va, feats, oc, 0)
            f1 = f1_score(va.classe, prever(va), average="macro")
            print(f"{nome}, {oc} neurônios: F1 validação {f1:.3f}")
            if melhor is None or f1 > melhor[0] + 0.005:   # empate: fica com a rede menor
                melhor = (f1, oc, m, media, desvio, prever, feats)
        modelos[nome] = melhor

    y = te.classe.values
    pred = {"Balanço + limiares": te.classe_balanco_placa.values,
            f"Rede sem situação ({len(sem_ind)}-{modelos['sem_ind'][1]}-3)": modelos["sem_ind"][5](te),
            f"**Rede v3 com situação** ({len(todas)}-{modelos['v3'][1]}-3)": modelos["v3"][5](te)}
    # híbrido: com sensor de vazão (irrigação confiável) usa o balanço; nas outras fontes, a v3
    p3 = pred[list(pred)[2]]
    pred["Híbrido (balanço com sensor, v3 nas outras)"] = np.where(te.fonte.values == "sensor",
                                                                     te.classe_balanco_placa.values, p3)

    os.makedirs(PASTA, exist_ok=True)
    _, oc, m, media, desvio, _, feats = modelos["v3"]
    n_par = t.exportar(os.path.join(PASTA, "agroedge_pesos_v3.py"), feats, oc, media, desvio, m)

    cab = "| método | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |\n|---|---|---|---|---|---|\n"
    out = ["# Classificador v3 (modelo único): teste nos cenários de 2009\n\n",
           f"Dataset: {len(df)} dias, {df.cenario.nunique()} cenários; teste: {len(te)} dias, "
           f"{te.cenario.nunique()} cenários. Rótulo = balanço FAO-56 com os dados verdadeiros. "
           "Entradas = o que a placa veria, mais a situação do local (fonte da irrigação e início do uso).\n\n"
           "## Geral\n\n", cab]
    for nome, p in pred.items():
        out.append(t.linha(nome, t.metricas(y, p)))

    def tabela(titulo, mascaras):
        out.append(f"\n## Por {titulo} (acurácia; entre parênteses, crítico detectado)\n\n")
        out.append(f"| {titulo} | dias | " + " | ".join(pred) + " |\n|---|---|" + "---|" * len(pred) + "\n")
        for rot, mask in mascaras:
            if mask.sum() == 0:
                continue
            cel = [f"{t.metricas(y[mask], p[mask])['acc']:.3f} ({t.metricas(y[mask], p[mask])['rec_crit']:.2f})"
                   for p in pred.values()]
            out.append(f"| {rot} | {mask.sum()} | " + " | ".join(cel) + " |\n")

    tabela("fonte da irrigação", [(r, (te.fonte == k).values) for k, r in FONTES.items()])
    tabela("início do uso", [(r, (te.inicio_tipo == k).values) for k, r in INICIOS.items()])

    out.append("\n## Rede v3 por combinação (acurácia)\n\n| fonte da irrigação | " +
               " | ".join(INICIOS.values()) + " |\n|---|" + "---|" * len(INICIOS) + "\n")
    for kf, rf in FONTES.items():
        cel = []
        for ki in INICIOS:
            mask = ((te.fonte == kf) & (te.inicio_tipo == ki)).values
            cel.append(f"{(y[mask] == p3[mask]).mean():.3f} ({mask.sum()} dias)" if mask.sum() else "—")
        out.append(f"| {rf} | " + " | ".join(cel) + " |\n")

    out.append("\n## Matriz de confusão da rede v3 (linhas = real, colunas = predito)\n\n")
    out.append(pd.DataFrame(confusion_matrix(y, p3), index=NOMES, columns=NOMES).to_markdown() + "\n")
    out.append(f"\nParâmetros da v3: {n_par} (+{2 * len(feats)} de normalização), "
               f"{(n_par + 2 * len(feats)) * 4} bytes em array('f').\n")
    texto = "".join(out)
    with open(os.path.join(AQUI, "resultados_v3.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
