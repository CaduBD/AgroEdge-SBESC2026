# Classificador geral v2: resultado no teste (cenários de 2009)

Dataset: 70769 dias, 571 cenários; teste: 4201 dias, 35 cenários. Rótulo = balanço FAO-56 com os dados verdadeiros; entradas = o que a placa veria (irrigação mal registrada, ET0 e chuva com erro, TAW estimado, placa ligada no meio do ciclo).

## Geral

| método | acurácia | F1 macro | rec. adequado | rec. moderado | rec. crítico |
|---|---|---|---|---|---|
| Balanço da placa + limiares (sem rede) | 0.644 | 0.596 | 0.618 | 0.410 | 0.921 |
| Rede v2 com balanço (37-16-3) | 0.705 | 0.680 | 0.650 | 0.675 | 0.877 |
| Rede v2 sem balanço (34-32-3) | 0.689 | 0.669 | 0.622 | 0.692 | 0.866 |

## Por cultura (acurácia; entre parênteses, revocação do crítico)

| cultura | dias | Balanço da placa + limiares (sem rede) | Rede v2 com balanço (37-16-3) | Rede v2 sem balanço (34-32-3) |
|---|---|---|---|---|
| sintéticas | 2654 | 0.606 (0.86) | 0.677 (0.88) | 0.650 (0.82) |
| uva Itália | 534 | 0.554 (0.92) | 0.665 (0.82) | 0.661 (0.83) |
| manga Tommy Atkins | 1013 | 0.792 (0.99) | 0.797 (0.89) | 0.808 (0.93) |

## Por registro da irrigação (acurácia; entre parênteses, revocação do crítico)

| registro da irrigação | dias | Balanço da placa + limiares (sem rede) | Rede v2 com balanço (37-16-3) | Rede v2 sem balanço (34-32-3) |
|---|---|---|---|---|
| completo | 1132 | 0.934 (0.99) | 0.888 (0.88) | 0.845 (0.91) |
| parcial | 1347 | 0.683 (0.85) | 0.742 (0.90) | 0.733 (0.89) |
| nunca registra | 1722 | 0.423 (0.96) | 0.555 (0.83) | 0.553 (0.78) |

## Por início do uso (acurácia; entre parênteses, revocação do crítico)

| início do uso | dias | Balanço da placa + limiares (sem rede) | Rede v2 com balanço (37-16-3) | Rede v2 sem balanço (34-32-3) |
|---|---|---|---|---|
| ligada no início do ciclo | 2090 | 0.651 (0.99) | 0.664 (0.89) | 0.664 (0.87) |
| ligada no meio do ciclo | 2111 | 0.637 (0.84) | 0.745 (0.87) | 0.715 (0.86) |

## Matriz de confusão da rede v2 com balanço (linhas = real, colunas = predito)

|          |   adequado |   moderado |   critico |
|:---------|-----------:|-----------:|----------:|
| adequado |       1595 |        537 |       323 |
| moderado |         78 |        554 |       189 |
| critico  |          1 |        113 |       811 |

Parâmetros da rede v2 com balanço: 659 (+74 de normalização), 2932 bytes em array('f'). Pesos em versoes/v2_geral/.

Referência v1 (só uva, irrigação sempre certa, placa ligada desde a poda): 90,9% de acurácia e 95,0% do crítico (resultados_mlp.md). Não é comparável direto: a v1 não foi testada com dados faltando nem com outras culturas.
