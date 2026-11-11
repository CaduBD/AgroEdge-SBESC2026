# Modelo v3 (candidato): MLP 45-16-3, modelo único com entradas de situação

Gerado em 11/11/2026 por `modelo/12_gerar_dataset_v3.py` + `modelo/13_treinar_v3.py`.
**Não está em uso no firmware** (continua o v1, `versoes/v1_uva_39f/`).

- 37 entradas de clima, cultura e balanço (as mesmas da v2) + 8 de situação, que viriam do `config_local`/dashboard:
  `irr_sensor`, `irr_manual`, `irr_tempo`, `irr_parcial`, `irr_nenhuma` (de onde vem a irrigação) e
  `inicio_ciclo`, `inicio_apos_irr`, `inicio_meio` (como a placa foi instalada). Uma delas vale 1 em cada grupo.
- Resultado: `resultados_v3.md` (cópia nesta pasta). Discussão: `modelo/DECISOES.md`, seção 15.

Comparação com as outras versões, proposta e decisões pendentes: [`../README.md`](../README.md).
