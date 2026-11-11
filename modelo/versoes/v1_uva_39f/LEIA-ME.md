# Modelo v1: MLP 39-16-3, só uva Itália (backup de 10/11/2026)

Cópia do classificador que está em uso no firmware antes do retreino geral (várias culturas e dados faltando).
Commit de referência: `70fa5f9` (tag git `modelo-v1-uva`).

- `agroedge_pesos.py`: pesos, médias e desvios (gerado pelo `03_treinar_mlp.py`).
- `historico.py` e `classificador.py`: montam as 39 entradas e fazem a inferência na placa.
- `01_gerar_dataset.py` e `03_treinar_mlp.py`: os scripts que geraram este modelo.
- `resultados_mlp.md`: teste em 2009: acurácia 90,9%, F1 macro 0,891, revocação do crítico 95,0%.

Para voltar a este modelo na placa: copie `agroedge_pesos.py`, `historico.py` e `classificador.py` desta pasta
para `firmware/modelo/` (ou `git checkout modelo-v1-uva -- firmware/modelo/agroedge_pesos.py firmware/modelo/historico.py firmware/modelo/classificador.py`).

Comparação com as outras versões e decisões pendentes: [`../README.md`](../README.md).
