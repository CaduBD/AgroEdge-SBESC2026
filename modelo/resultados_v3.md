# Classificador v3 (modelo único): teste nos cenários de 2009

Dataset: 119896 dias, 1146 cenários; teste: 7401 dias, 72 cenários. Rótulo = balanço FAO-56 com os dados verdadeiros. Entradas = o que a placa veria, mais a situação do local (fonte da irrigação e início do uso).

## Geral

| método | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |
|---|---|---|---|---|---|
| Balanço + limiares | 0.764 | 0.714 | 0.771 | 0.665 | 0.922 |
| Rede sem situação (37-16-3) | 0.772 | 0.720 | 0.778 | 0.713 | 0.850 |
| **Rede v3 com situação** (45-16-3) | 0.794 | 0.744 | 0.796 | 0.783 | 0.801 |
| Híbrido (balanço com sensor, v3 nas outras) | 0.800 | 0.751 | 0.807 | 0.781 | 0.801 |

## Por fonte da irrigação (acurácia; entre parênteses, crítico detectado)

| fonte da irrigação | dias | Balanço + limiares | Rede sem situação (37-16-3) | **Rede v3 com situação** (45-16-3) | Híbrido (balanço com sensor, v3 nas outras) |
|---|---|---|---|---|---|
| sensor de vazão | 1110 | 0.876 (0.90) | 0.867 (0.86) | 0.833 (0.90) | 0.876 (0.90) |
| produtor informa a quantidade | 1615 | 0.837 (0.65) | 0.830 (0.55) | 0.844 (0.76) | 0.844 (0.76) |
| produtor informa o tempo de válvula | 1767 | 0.864 (0.97) | 0.879 (0.89) | 0.874 (0.95) | 0.874 (0.95) |
| registro de vez em quando | 1611 | 0.747 (0.97) | 0.730 (0.83) | 0.785 (0.72) | 0.785 (0.72) |
| sem informação | 1298 | 0.464 (0.97) | 0.523 (0.99) | 0.599 (0.24) | 0.599 (0.24) |

## Por início do uso (acurácia; entre parênteses, crítico detectado)

| início do uso | dias | Balanço + limiares | Rede sem situação (37-16-3) | **Rede v3 com situação** (45-16-3) | Híbrido (balanço com sensor, v3 nas outras) |
|---|---|---|---|---|---|
| no início do ciclo | 3390 | 0.778 (0.97) | 0.773 (0.88) | 0.787 (0.91) | 0.797 (0.91) |
| no meio, logo após irrigação | 1937 | 0.756 (0.92) | 0.790 (0.87) | 0.835 (0.55) | 0.831 (0.54) |
| no meio, dia qualquer | 2074 | 0.749 (0.74) | 0.751 (0.70) | 0.767 (0.75) | 0.777 (0.75) |

## Rede v3 por combinação (acurácia)

| fonte da irrigação | no início do ciclo | no meio, logo após irrigação | no meio, dia qualquer |
|---|---|---|---|
| sensor de vazão | 0.884 (553 dias) | 0.938 (129 dias) | 0.736 (428 dias) |
| produtor informa a quantidade | 0.828 (569 dias) | 0.863 (446 dias) | 0.845 (600 dias) |
| produtor informa o tempo de válvula | 0.899 (1024 dias) | 0.843 (401 dias) | 0.836 (342 dias) |
| registro de vez em quando | 0.759 (705 dias) | 0.872 (374 dias) | 0.759 (532 dias) |
| sem informação | 0.466 (539 dias) | 0.761 (587 dias) | 0.459 (172 dias) |

## Matriz de confusão da rede v3 (linhas = real, colunas = predito)

|          |   adequado |   moderado |   critico |
|:---------|-----------:|-----------:|----------:|
| adequado |       3811 |        638 |       337 |
| moderado |        190 |       1364 |       187 |
| critico  |         13 |        161 |       700 |

Parâmetros da v3: 787 (+90 de normalização), 3508 bytes em array('f').
