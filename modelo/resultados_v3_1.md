# Classificador v3.1 (v3 + manga Palmer): teste nos cenários de 2009

Dataset: 190704 dias, 1125 cenários; teste: 7882 dias, 62 cenários (4 de Palmer). Mesmas falhas de campo da v3 (fonte da irrigação e início do uso sorteados).

## Geral

| método | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |
|---|---|---|---|---|---|
| Balanço + limiares | 0.710 | 0.650 | 0.726 | 0.485 | 0.912 |
| Rede v3.1 (45-32-3) | 0.768 | 0.704 | 0.813 | 0.534 | 0.873 |
| Híbrido (balanço com sensor, v3.1 nas outras) | 0.771 | 0.707 | 0.818 | 0.532 | 0.875 |

## Por cultura (acurácia; entre parênteses, crítico detectado)

| cultura | dias | Balanço + limiares | Rede v3.1 (45-32-3) | Híbrido (balanço com sensor, v3.1 nas outras) |
|---|---|---|---|---|
| sintéticas | 4951 | 0.729 (0.90) | 0.774 (0.89) | 0.779 (0.89) |
| uva Itália | 734 | 0.766 (1.00) | 0.834 (0.75) | 0.832 (0.75) |
| manga Tommy Atkins | 1244 | 0.761 (0.93) | 0.825 (0.87) | 0.827 (0.87) |
| **manga Palmer (ano todo)** | 953 | 0.504 (0.98) | 0.608 (0.70) | 0.608 (0.70) |

## Manga Palmer por fonte da irrigação (acurácia: balanço / rede v3.1)

| fonte | dias | balanço | rede v3.1 |
|---|---|---|---|
| produtor informa a quantidade | 238 | 0.824 | 0.903 |
| sem informação | 715 | 0.397 | 0.509 |

## Matriz de confusão da rede v3.1 só na Palmer (linhas = real, colunas = predito)

|          |   adequado |   moderado |   critico |
|:---------|-----------:|-----------:|----------:|
| adequado |        503 |         37 |        76 |
| moderado |        122 |         19 |       115 |
| critico  |         19 |          5 |        57 |

Parâmetros: 1571 (+90 de normalização). Pesos em versoes/v3_1_palmer/.
