"""
AgroEdge - treino e teste do classificador GERAL (v2), com o dataset do 06_gerar_dataset_geral.py.

Compara, no teste (cenários de 2009), com os mesmos dados incompletos que a placa veria:
  - balanço da placa + limiares (a conta do lamina.py, sem rede): a linha de base;
  - rede v2 com todas as entradas (inclui o balanço da placa, que ela pode corrigir);
  - rede v2 sem as entradas do balanço da placa (só clima e somas), para ver o que cada parte faz.
E abre o resultado por cultura, por tipo de registro da irrigação e por início do uso.

Não mexe no firmware: grava os pesos candidatos em versoes/v2_geral/ e o relatório em
resultados_mlp_geral.md. O modelo em uso continua o v1 até a decisão de trocar.

Uso: python3 07_treinar_mlp_geral.py   (depois do 06)
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import accuracy_score, f1_score, recall_score, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
gerar = import_module("06_gerar_dataset_geral")
PASTA_V2 = os.path.join(AQUI, "versoes", "v2_geral")
CLASSES = ("adequado", "deficit_moderado", "deficit_critico")
NOMES = ["adequado", "moderado", "critico"]
BALANCO = ["deficit_placa_taw", "deficit_placa_raw", "ks_placa"]
OCULTAS = (16, 32)
SEMENTES = (0, 1, 2)


def treinar(tr, va, feats, oculta, semente):
    tf.keras.utils.set_random_seed(semente)
    media = tr[feats].mean().values.astype(np.float32)
    desvio = tr[feats].std(ddof=0).values.astype(np.float32)
    desvio[desvio == 0] = 1.0
    norm = lambda d: ((d[feats].values - media) / desvio).astype(np.float32)
    pesos = dict(enumerate(compute_class_weight("balanced", classes=np.arange(3), y=tr.classe.values)))
    m = tf.keras.Sequential([tf.keras.Input(shape=(len(feats),)),
                             tf.keras.layers.Dense(oculta, activation="relu"),
                             tf.keras.layers.Dense(3, activation="softmax")])
    m.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy")
    m.fit(norm(tr), tr.classe.values, validation_data=(norm(va), va.classe.values), epochs=300,
          batch_size=128, class_weight=pesos, verbose=0,
          callbacks=[tf.keras.callbacks.EarlyStopping(patience=20, restore_best_weights=True)])
    prever = lambda d: m.predict(norm(d), verbose=0).argmax(1)
    return m, media, desvio, prever


def metricas(y, p):
    rec = recall_score(y, p, average=None, labels=[0, 1, 2], zero_division=0)
    return dict(acc=accuracy_score(y, p), f1=f1_score(y, p, average="macro"),
                rec_ad=rec[0], rec_mod=rec[1], rec_crit=rec[2])


def linha(nome, m):
    return (f"| {nome} | {m['acc']:.3f} | {m['f1']:.3f} | {m['rec_ad']:.3f} | {m['rec_mod']:.3f} | "
            f"{m['rec_crit']:.3f} |\n")


def exportar(caminho, feats, oculta, media, desvio, modelo):
    (W1, B1), (W2, B2) = (c.get_weights() for c in modelo.layers)
    lista = lambda v: 'array("f", [' + ", ".join(f"{x:.8g}" for x in np.asarray(v, np.float32).ravel()) + "])"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Gerado por modelo/07_treinar_mlp_geral.py - não editar à mão\n")
        f.write("# Candidato v2 (várias culturas e dados faltando). NÃO está em uso no firmware.\n")
        f.write("from array import array\n\n")
        f.write(f"N_FEATURES = {len(feats)}\nN_OCULTA = {oculta}\nN_CLASSES = 3\n\n")
        f.write("FEATURES = (" + ", ".join(f'"{n}"' for n in feats) + ")\n")
        f.write("CLASSES = (" + ", ".join(f'"{c}"' for c in CLASSES) + ")\n\n")
        f.write(f"MEDIA = {lista(media)}\nDESVIO = {lista(desvio)}\n\n")
        f.write(f"W1 = {lista(W1)}\nB1 = {lista(B1)}\n\nW2 = {lista(W2)}\nB2 = {lista(B2)}\n")
    return W1.size + B1.size + W2.size + B2.size


def main():
    df = pd.read_csv(gerar.SAIDA)
    todas = [c for c in df.columns if c not in (
        "data", "cenario", "cultura", "registro", "inicio_meio", "dia_ciclo", "Dr", "TAW_real",
        "classe", "classe_balanco_placa", "ano", "split")]
    sem_bal = [c for c in todas if c not in BALANCO]
    tr, va, te = (df[df.split == s] for s in ("treino", "validacao", "teste"))

    # escolhe o tamanho da camada pela validação (média de 3 sementes)
    escolha = {}
    for nome, feats in (("com balanço", todas), ("sem balanço", sem_bal)):
        melhor = None
        for oc in OCULTAS:
            f1s = []
            for s in SEMENTES:
                _, _, _, prever = treinar(tr, va, feats, oc, s)
                f1s.append(f1_score(va.classe, prever(va), average="macro"))
            print(f"{nome}, {oc} neurônios: F1 validação {np.mean(f1s):.3f} ± {np.std(f1s):.3f}")
            if melhor is None or np.mean(f1s) > melhor[1]:
                melhor = (oc, np.mean(f1s))
        escolha[nome] = melhor[0]

    # modelo final de cada variante (semente 0) e teste
    final = {}
    for nome, feats in (("com balanço", todas), ("sem balanço", sem_bal)):
        m, media, desvio, prever = treinar(tr, va, feats, escolha[nome], 0)
        final[nome] = (m, media, desvio, prever, feats)
    pred = {"Balanço da placa + limiares (sem rede)": te.classe_balanco_placa.values,
            f"Rede v2 com balanço ({len(todas)}-{escolha['com balanço']}-3)": final["com balanço"][3](te),
            f"Rede v2 sem balanço ({len(sem_bal)}-{escolha['sem balanço']}-3)": final["sem balanço"][3](te)}
    y = te.classe.values

    os.makedirs(PASTA_V2, exist_ok=True)
    m, media, desvio, _, feats = final["com balanço"]
    n_par = exportar(os.path.join(PASTA_V2, "agroedge_pesos_v2.py"), feats, escolha["com balanço"],
                     media, desvio, m)

    cab = "| método | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |\n|---|---|---|---|---|---|\n"
    out = ["# Classificador geral v2: resultado no teste (cenários de 2009)\n\n",
           f"Dataset: {len(df)} dias, {df.cenario.nunique()} cenários; teste: {len(te)} dias, "
           f"{te.cenario.nunique()} cenários. Rótulo = balanço FAO-56 com os dados verdadeiros; "
           "entradas = o que a placa veria (irrigação mal registrada, ET0 e chuva com erro, TAW "
           "estimado, placa ligada no meio do ciclo).\n\n## Geral\n\n", cab]
    for nome, p in pred.items():
        out.append(linha(nome, metricas(y, p)))

    def recorte(titulo, coluna, rotulos):
        out.append(f"\n## Por {titulo} (acurácia; entre parênteses, revocação do crítico)\n\n")
        out.append("| " + titulo + " | dias | " + " | ".join(pred) + " |\n")
        out.append("|---|---|" + "---|" * len(pred) + "\n")
        for valor, rot in rotulos:
            mask = (te[coluna] == valor).values
            if mask.sum() == 0:
                continue
            cel = []
            for p in pred.values():
                mm = metricas(y[mask], p[mask])
                cel.append(f"{mm['acc']:.3f} ({mm['rec_crit']:.2f})")
            out.append(f"| {rot} | {mask.sum()} | " + " | ".join(cel) + " |\n")

    recorte("cultura", "cultura", [("sintetica", "sintéticas"), ("uva_italia", "uva Itália"),
                                   ("manga_tommy_atkins", "manga Tommy Atkins")])
    recorte("registro da irrigação", "registro", [("completo", "completo"), ("parcial", "parcial"),
                                                  ("nunca", "nunca registra")])
    recorte("início do uso", "inicio_meio", [(0, "ligada no início do ciclo"),
                                             (1, "ligada no meio do ciclo")])

    p2 = list(pred.values())[1]
    out.append("\n## Matriz de confusão da rede v2 com balanço (linhas = real, colunas = predito)\n\n")
    out.append(pd.DataFrame(confusion_matrix(y, p2), index=NOMES, columns=NOMES).to_markdown() + "\n")
    out.append(f"\nParâmetros da rede v2 com balanço: {n_par} (+{2 * len(feats)} de normalização), "
               f"{(n_par + 2 * len(feats)) * 4} bytes em array('f'). Pesos em versoes/v2_geral/.\n")
    out.append("\nReferência v1 (só uva, irrigação sempre certa, placa ligada desde a poda): 90,9% de "
               "acurácia e 95,0% do crítico (resultados_mlp.md). Não é comparável direto: a v1 não "
               "foi testada com dados faltando nem com outras culturas.\n")
    texto = "".join(out)
    with open(os.path.join(AQUI, "resultados_mlp_geral.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
