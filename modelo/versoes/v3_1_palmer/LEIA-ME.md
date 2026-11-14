# Modelo v3.1 (candidato): v3 retreinada com a manga Palmer

Gerado em 14/11/2026 por `modelo/14_v3_1_palmer.py`; avaliado na Palmer por `modelo/15_avaliar_palmer.py`.
**Não está em uso no firmware** (continua o v1, `versoes/v1_uva_39f/`).

- Mesmas 45 entradas da v3 (37 de clima, cultura e balanço + 8 de situação: fonte da irrigação e início do uso).
- Diferenças para a v3: a manga Palmer (ano todo, `culturas.py`) entra entre as culturas reais (uva, Tommy Atkins e
  Palmer, 10% cada) e o ciclo das culturas sintéticas vai de 90 a 365 dias (antes 90 a 200).
- Rede 45-32-3 (escolhida pela validação), 1.571 parâmetros, 6,6 KB em array('f').
- Resultados: `resultados_v3_1.md` (teste geral de 2009) e `resultados_v3_1_palmer.md` (150 ciclos de Palmer).
  Discussão: `modelo/DECISOES.md`, seção 17. Comparação com as outras versões: [`../README.md`](../README.md).
