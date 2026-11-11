# MLP 39-16-3: Keras × classificador.py (teste = 2009)

| versão | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |
|---|---|---|---|---|---|
| Keras (float32) | 0.909 | 0.891 | 0.935 | 0.835 | 0.950 |
| classificador.py (MicroPython) | 0.909 | 0.891 | 0.935 | 0.835 | 0.950 |

Concordância Keras × classificador.py: 1.0000.
Parâmetros da rede: 691, mais 78 de normalização; em array('f') ocupam 3076 bytes.

A conferência roda no PC (CPython); na placa o MicroPython calcula em float32, o que pode mudar o último dígito das saídas, mas não deve mudar a classe.

## Matriz de confusão (linhas = real, colunas = predito)

|          |   adequado |   moderado |   critico |
|:---------|-----------:|-----------:|----------:|
| adequado |       2281 |        159 |         0 |
| moderado |        119 |        879 |        55 |
| critico  |          0 |         16 |       306 |
