# Modelo v2 (candidato): MLP 37-16-3, várias culturas e dados faltando

Gerado em 10/11/2026 por `modelo/06_gerar_dataset_geral.py` + `modelo/07_treinar_mlp_geral.py`.
**Não está em uso no firmware.** O firmware continua com o v1 (`versoes/v1_uva_39f/`, tag `modelo-v1-uva`).

- `agroedge_pesos_v2.py`: pesos, médias e desvios. As 37 entradas estão em `FEATURES` e são montadas pela
  classe `PlacaGeral` do script 06 (para usar na placa, o `historico.py` precisa ser adaptado a elas).
- Resultado no teste (cenários de 2009): `resultados_mlp_geral.md` (cópia nesta pasta). Discussão: `modelo/DECISOES.md`, seção 14.

Comparação com as outras versões e decisões pendentes: [`../README.md`](../README.md).
