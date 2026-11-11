# AgroEdge: dataset e classificador de estado hídrico (uva Itália)

Por que o modelo é assim (MicroPython, TAW como entrada, poda em qualquer data): veja [DECISOES.md](DECISOES.md). Explicação passo a passo em [GUIA.md](GUIA.md) e linha por linha em [CODIGO_EXPLICADO.md](CODIGO_EXPLICADO.md).

> **Versões do classificador:** há três versões guardadas em [`versoes/`](versoes/): **v1** (só uva, em uso no firmware),
> **v2** e **v3** (várias culturas e dados de campo com falhas; candidatas). A comparação, a proposta e o que a equipe
> precisa decidir estão em [`versoes/README.md`](versoes/README.md). Este README descreve a v1 (scripts 01 a 04).

Rodar em ordem (Python 3, `pip install pandas scikit-learn tabulate tensorflow`):

1. `python3 01_gerar_dataset.py` gera `dados/dataset_uva.csv` a partir de `dados/petrolina_clima_2000_2009.csv` (50.903 dias rotulados, 467 ciclos com solo, raiz e poda sorteados).
2. `python3 02_comparar_modelos.py` treina MLP, SVM e Random Forest e gera `resultados_comparacao.md`.
3. `python3 03_treinar_mlp.py` treina a MLP final no Keras, gera `../firmware/modelo/agroedge_pesos.py` e confere o `classificador.py` no teste (`resultados_mlp.md`).
4. `python3 04_conferir_firmware.py` passa os dias de 2009 pelo caminho do firmware (`historico.py` → `classificador.py` → `lamina.py`), confere as entradas e simula a placa irrigando sozinha.
5. `python3 05_validar_eto.py` confere o ET0 do firmware (`eto.py`) contra o DataClimaBR (RMSE 0,07 mm/dia, R² 0,999).

Scripts 06 a 13 (versões v2 e v3 e experimentos de campo): ver a tabela em [`versoes/README.md`](versoes/README.md#9-como-reproduzir).

## Firmware (MicroPython)
Em `../firmware/modelo/`, copie para a placa:
- `agroedge_pesos.py`: pesos, bias, médias e desvios (gerado pelo script 03, não editar).
- `classificador.py`: a inferência da MLP em Python puro; use `classificador.classificar(x)`.
- `config_local.py`: **o único arquivo que muda por local**: cultura (`CULTURA`), data da poda ou floração (`DATA_REFERENCIA`), água disponível do solo, eficiência, área e vazão por planta. Calcula `taw()`, `dap(hoje)` e `kc(dap)` a partir da biblioteca `culturas.py`.
- `culturas.py`: biblioteca de culturas (Kc ao longo do ciclo, fração p, raiz e fonte de cada número). Hoje: uva Itália e manga Tommy Atkins.
- `historico.py`: guarda os últimos 28 dias e as somas desde a poda num JSON na flash e monta as 39 entradas do dia, com as mesmas contas do script 01.
- `lamina.py`: a lâmina de irrigação pelo FAO-56 (seção abaixo).
- `teste_classificador.py`: roda 6 dias de 2009 na placa e mostra classe, tempo e memória livre.

O modelo é geral: o TAW do solo é uma das entradas, então os mesmos pesos servem para qualquer solo com TAW entre 25 e 140 mm, sem retreinar. Roda em float, sem TensorFlow Lite nem quantização: são 691 parâmetros (3 KB em `array('f')`). Conferido no MicroPython 1.30 para Linux compilado com float de 32 bits, como no RP2040: mesma classe que o Keras nos 3.815 dias de teste (90,9% de acurácia, 95,0% dos críticos detectados). O tempo na BitDogLab ainda precisa ser medido com o `teste_classificador.py`.

## Lâmina de irrigação
Como na proposta, a lâmina sai do FAO-56 e a classe sai do modelo. A classe decide **se** irriga e o balanço decide **quanto**:
- `lamina.atualizar_deficit(...)`: o déficit do solo em mm, pela mesma conta do rótulo (eq. 84 e 85).
- `lamina.recomendar(classe, deficit)`: adequado não irriga; moderado ou crítico repõe todo o déficit. Devolve a lâmina líquida e a bruta (líquida ÷ eficiência).
- `lamina.tempo_min(bruta)`: minutos de válvula aberta, pela área e vazão do `config_local.py`.
- `lamina.litros_planta(mm)` e `lamina.litros_total(mm)`: a lâmina em litros por planta e na área toda (1 mm em 1 m² = 1 L; total = × `N_PLANTAS`).

Com a placa irrigando sozinha nos 35 ciclos de 2009 (script 04), o solo ficou adequado em 94,6% dos dias e não teve nenhum dia crítico, contra 64% e 8,4% dos produtores simulados do dataset.

## Regra de rotulagem
Balanço hídrico diário do solo do FAO-56 (cap. 8, eq. 84 e 85), sobre o clima real de Petrolina 2000–2009 (DataClimaBR):
`Dr(hoje) = Dr(ontem) − chuva − irrigação + Ks·Kc·ET₀`, limitado entre 0 e TAW, com TAW = 1000 × água disponível × raiz.

| Classe | Condição | Significado |
|---|---|---|
| adequado | Dr ≤ RAW | planta sem estresse (Ks = 1) |
| déficit moderado | RAW < Dr ≤ Dr(Ks = 0,5) | estresse leve a médio |
| déficit crítico | Dr > Dr(Ks = 0,5) | evapotranspiração caiu mais da metade |

A irrigação é **simulada**: cada ciclo tem um "produtor" sorteado, com regras diferentes (irrigar por gatilho de umidade ou em turno fixo, com lâminas e falhas variadas). É isso que gera as três classes; com só a chuva, Petrolina daria "crítico" quase o ano todo.

## Suposições (ASSUMIDO, a validar com o Prof. Max)
Ficam no topo do `01_gerar_dataset.py`; troque e rode de novo.
- Ciclo de 109 dias (Ávila Netto et al., 2000), com a poda em qualquer dia do ano. Dias fora do ciclo não entram.
- Água disponível sorteada entre 0,06 e 0,18 m³/m³ (de arenoso a Vertissolo, FAO-56 tab. 19) e raiz entre 0,4 e 0,8 m: TAW de 25 a 140 mm.
- Fração p = 0,35 para uva de mesa (FAO-56 tab. 22, conferir): RAW = 0,35 × TAW.
- Limite do crítico em Ks = 0,5.
- Os 2 dias faltantes no CSV (08/10/2000 e 14/10/2001) foram interpolados (coluna `interpolado`).

## Features (39, nesta ordem no firmware)
- TAW, dap, kc, ETo, ETc, chuva, irrigacao, Tmax, Tmin, UR, vento, radiacao, dias_sem_irrigar.
- Somas móveis de 3, 7 e 14 dias de ETc, chuva e irrigação, mais o saldo (chuva + irrigação − ETc) de 7 e 14 dias.
- ETc, chuva e saldo de 7, 14, 21 e 28 dias e desde a poda, divididos pelo TAW (em "tanques" do solo).

O firmware precisa saber a irrigação aplicada (registro da válvula ou hidrômetro) e guardar 28 dias de histórico. As janelas longas e as somas desde a poda subiram a acurácia de 84,6% para 90,9% ([DECISOES.md](DECISOES.md), seção 11).

## Divisão
Pelo ano da poda: treino 2000–2006, validação 2007–2008, teste 2009. Normalização calculada só no treino. Hiperparâmetros escolhidos pela validação (F1 macro).

## Limitações
- O rótulo é sintético: a acurácia mostra que o modelo aprende o balanço do FAO-56, não que acerta o campo. A prova real é com tensiômetros (Sprint 5).
- O clima vem de grade interpolada (BR-DWGD), não dos sensores do protótipo.
- A memória do SVM e da RF é estimativa dos parâmetros em float32, sem o código de inferência.
- Com o histórico completo, a placa calcula o mesmo Dr do rótulo pela fórmula, e limiares nesse Dr acertam 100% do rótulo sintético, contra 90,9% da rede. Ver [DECISOES.md](DECISOES.md), seção 10.
