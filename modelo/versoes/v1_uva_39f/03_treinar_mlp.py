"""
AgroEdge - treino da MLP final (Keras) e exportação para MicroPython.
Mesmo dataset, features e split do 02_comparar_modelos.py.

Gera:
  ../firmware/modelo/agroedge_pesos.py   pesos, bias, médias e desvios (lido por classificador.py)
  resultados_mlp.md                      Keras × classificador.py: acurácia, matriz de confusão, tamanho

Depois de gerar, roda o próprio classificador.py no conjunto de teste para conferir que ele
dá a mesma resposta que o Keras.

Uso: python3 03_treinar_mlp.py
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
PASTA_FW = os.path.join(AQUI, "..", "firmware", "modelo")
sys.path.insert(0, AQUI)
FEATURES = import_module("02_comparar_modelos").FEATURES
CLASSES = ("adequado", "deficit_moderado", "deficit_critico")
NOMES = ["adequado", "moderado", "critico"]
OCULTA = 16          # 1 camada de 16 neurônios (melhor F1 na validação do script 02)


def lista_f(v):
    """Vetor numpy -> texto 'array("f", [...])' com 8 algarismos (precisão do float32)."""
    nums = ", ".join(f"{x:.8g}" for x in np.asarray(v, dtype=np.float32).ravel())
    return f'array("f", [{nums}])'


def exportar(media, desvio, W1, B1, W2, B2):
    os.makedirs(PASTA_FW, exist_ok=True)
    caminho = os.path.join(PASTA_FW, "agroedge_pesos.py")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Gerado por modelo/03_treinar_mlp.py - não editar à mão\n")
        f.write("from array import array\n\n")
        f.write(f"N_FEATURES = {len(FEATURES)}\nN_OCULTA = {OCULTA}\nN_CLASSES = {len(CLASSES)}\n\n")
        f.write("FEATURES = (" + ", ".join(f'"{n}"' for n in FEATURES) + ")\n")
        f.write("CLASSES = (" + ", ".join(f'"{c}"' for c in CLASSES) + ")\n\n")
        f.write("# normalização (calculada só no treino)\n")
        f.write(f"MEDIA = {lista_f(media)}\nDESVIO = {lista_f(desvio)}\n\n")
        f.write("# camada escondida: W1[i * N_OCULTA + j] liga a entrada i ao neurônio j\n")
        f.write(f"W1 = {lista_f(W1)}\nB1 = {lista_f(B1)}\n\n")
        f.write("# camada de saída: W2[j * N_CLASSES + k] liga o neurônio j à classe k\n")
        f.write(f"W2 = {lista_f(W2)}\nB2 = {lista_f(B2)}\n")
    return caminho


def main():
    tf.keras.utils.set_random_seed(0)
    df = pd.read_csv(os.path.join(AQUI, "dados", "dataset_uva.csv"))
    tr, va, te = (df[df.split == s] for s in ("treino", "validacao", "teste"))
    media = tr[FEATURES].mean().values.astype(np.float32)
    desvio = tr[FEATURES].std(ddof=0).values.astype(np.float32)
    norm = lambda d: ((d[FEATURES].values - media) / desvio).astype(np.float32)
    Xtr, Xva, Xte = norm(tr), norm(va), norm(te)
    ytr, yva, yte = tr.classe.values, va.classe.values, te.classe.values
    pesos = dict(enumerate(compute_class_weight("balanced", classes=np.arange(3), y=ytr)))

    modelo = tf.keras.Sequential([
        tf.keras.Input(shape=(len(FEATURES),)),
        tf.keras.layers.Dense(OCULTA, activation="relu"),
        tf.keras.layers.Dense(len(CLASSES), activation="softmax"),
    ])
    modelo.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                   loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    modelo.fit(Xtr, ytr, validation_data=(Xva, yva), epochs=200, batch_size=64,
               class_weight=pesos, verbose=0,
               callbacks=[tf.keras.callbacks.EarlyStopping(patience=15, restore_best_weights=True)])
    p_keras = modelo.predict(Xte, verbose=0).argmax(1)

    (W1, B1), (W2, B2) = (camada.get_weights() for camada in modelo.layers)
    caminho = exportar(media, desvio, W1, B1, W2, B2)

    # confere: roda o classificador.py de verdade (o mesmo que vai para a placa) no teste,
    # com as features sem normalizar, como o firmware vai receber
    sys.path.insert(0, PASTA_FW)
    clf = import_module("classificador")
    p_mcu = np.array([clf.classificar(list(x))[0] for x in te[FEATURES].values.astype(np.float32)])

    n_param = W1.size + B1.size + W2.size + B2.size
    with open(os.path.join(AQUI, "resultados_mlp.md"), "w", encoding="utf-8") as f:
        f.write(f"# MLP {len(FEATURES)}-{OCULTA}-3: Keras × classificador.py (teste = 2009)\n\n")
        f.write("| versão | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |\n"
                "|---|---|---|---|---|---|\n")
        for nome, p in (("Keras (float32)", p_keras), ("classificador.py (MicroPython)", p_mcu)):
            rec = recall_score(yte, p, average=None)
            f.write(f"| {nome} | {accuracy_score(yte, p):.3f} | {f1_score(yte, p, average='macro'):.3f} | "
                    f"{rec[0]:.3f} | {rec[1]:.3f} | {rec[2]:.3f} |\n")
        f.write(f"\nConcordância Keras × classificador.py: {(p_keras == p_mcu).mean():.4f}.\n")
        f.write(f"Parâmetros da rede: {n_param}, mais {2 * len(FEATURES)} de normalização; "
                f"em array('f') ocupam {(n_param + 2 * len(FEATURES)) * 4} bytes.\n\n")
        f.write("A conferência roda no PC (CPython); na placa o MicroPython calcula em float32, "
                "o que pode mudar o último dígito das saídas, mas não deve mudar a classe.\n\n")
        f.write("## Matriz de confusão (linhas = real, colunas = predito)\n\n")
        f.write(pd.DataFrame(confusion_matrix(yte, p_mcu), index=NOMES, columns=NOMES).to_markdown() + "\n")
    print(f"gerado: {caminho}")
    print(open(os.path.join(AQUI, "resultados_mlp.md"), encoding="utf-8").read())


if __name__ == "__main__":
    main()
