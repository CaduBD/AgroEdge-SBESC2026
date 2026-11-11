# AgroEdge - classificador de estado hídrico em MicroPython (BitDogLab / RP2040).
# Escrito à mão. Os números da rede ficam em agroedge_pesos.py, gerado por
# modelo/03_treinar_mlp.py; para trocar o modelo, gere esse arquivo de novo.
#
# Uso:
#   import classificador
#   classe, saidas = classificador.classificar(x)   # x na ordem de FEATURES
#   print(classificador.CLASSES[classe])

import agroedge_pesos as P

FEATURES = P.FEATURES
CLASSES = P.CLASSES


def classificar(x):
    """Recebe as N_FEATURES entradas do dia (sem normalizar) e devolve
    (índice da classe, lista com a saída de cada classe)."""
    if len(x) != P.N_FEATURES:
        raise ValueError("esperava %d features" % P.N_FEATURES)

    # 1. normalização, igual à do treino: (x - média) / desvio
    z = [(x[i] - P.MEDIA[i]) / P.DESVIO[i] for i in range(P.N_FEATURES)]

    # 2. camada escondida: h = ReLU(z · W1 + B1)
    h = []
    for j in range(P.N_OCULTA):
        s = P.B1[j]
        for i in range(P.N_FEATURES):
            s += z[i] * P.W1[i * P.N_OCULTA + j]
        h.append(s if s > 0.0 else 0.0)

    # 3. camada de saída: y = h · W2 + B2 (o softmax não muda qual é a maior)
    saidas = []
    melhor = 0
    for k in range(P.N_CLASSES):
        s = P.B2[k]
        for j in range(P.N_OCULTA):
            s += h[j] * P.W2[j * P.N_CLASSES + k]
        saidas.append(s)
        if s > saidas[melhor]:
            melhor = k

    # 4. a classe é a saída de maior valor (argmax)
    return melhor, saidas
