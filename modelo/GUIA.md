# Guia passo a passo: como o modelo do AgroEdge funciona

Este guia explica, na ordem em que as coisas acontecem, tudo o que está em `modelo/` e em `firmware/modelo/`.

## 0. A ideia geral

O fluxo inteiro é uma linha de montagem:

```
clima real de Petrolina (CSV)
   → 01: sorteia solo, raiz, data de poda e produtor; calcula a água no solo dia a dia → rótulo
   → 02: treina MLP, SVM e Random Forest e compara
   → 03: treina a MLP final e exporta os pesos para MicroPython
   → firmware/modelo/: classificador.py + agroedge_pesos.py + config_local.py, o que a BitDogLab usa
```

O modelo é **geral**: o mesmo arquivo de pesos serve para qualquer área do Vale. O que muda de um local para outro (cultura, tipo de solo, raiz e data da poda ou floração) fica no `config_local.py` da placa, e o TAW do solo entra como uma das entradas da rede.

A pergunta que o classificador responde é: **"com o clima e a irrigação dos últimos dias, como está a água no solo hoje?"**

---

## 1. `01_gerar_dataset.py`: criar os dados rotulados

### 1.1 Por que precisamos simular
Para treinar um classificador, cada dia precisa de uma resposta certa (o rótulo). Não temos medição de umidade do solo de 2000 a 2009, então calculamos essa resposta com o **balanço hídrico do FAO-56**, que é o método padrão da agronomia. E como numa cultura irrigada quem define o estado do solo é a irrigação, simulamos produtores irrigando de jeitos diferentes.

### 1.2 Os parâmetros (topo do arquivo)
| Parâmetro | Valor | O que é |
|---|---|---|
| `CICLO_DIAS` | 109 | duração do ciclo, de Ávila Netto et al. (2000) |
| `CICLOS_POR_ANO` | 48 | quantos ciclos simulados começam em cada ano |
| `AGUA_DISP_FAIXA` | 0,06 a 0,18 m³/m³ | faixa sorteada de água que o solo segura, de arenoso a Vertissolo (ASSUMIDO) |
| `ZR_FAIXA` | 0,4 a 0,8 m | faixa sorteada de profundidade das raízes (ASSUMIDO) |
| `P_DEPLECAO` | 0,35 | fração que a planta tira sem sofrer (FAO-56, ASSUMIDO) |
| `KS_CRITICO` | 0,5 | a partir de onde chamamos de crítico (ASSUMIDO) |
| `SEMENTE` | 42 | faz o sorteio sair sempre igual (resultado reproduzível) |

Solo e raiz não são números fixos: cada ciclo sorteia os seus. Assim o modelo vê de tudo, do solo arenoso de Petrolina ao Vertissolo de Juazeiro, e aprende a usar o TAW que recebe.

### 1.2.1 `solo(agua_disp, zr)`: o "tanque de água" do solo
Com a água disponível e a raiz de um ciclo, calcula três números:

- **TAW** (água total disponível) = 1000 × água × raiz. É o tanque cheio. Exemplo com 0,11 e 0,6 m: **66 mm**.
- **RAW** (água facilmente disponível) = 0,35 × TAW. Até gastar isso, a planta não sofre. No exemplo: **23,1 mm**.
- **Dr crítico** = TAW − 0,5 × (1 − 0,35) × TAW. Passando disso, a planta transpira menos da metade do normal. No exemplo: **44,5 mm**.

Pense no solo como uma caixa d'água do tamanho do TAW. `Dr` (depleção) é **quanto já foi gasto**. Dr = 0 é caixa cheia; Dr = TAW é caixa vazia. Nos ciclos simulados o TAW vai de 25 a 140 mm.

### 1.3 `kc_uva(dap)`
A equação de Ávila Netto: `Kc = −0,00008·DAP² + 0,0089·DAP + 0,488`. DAP é o dia depois da poda (0 a 108). O Kc começa em 0,49, sobe até ~0,74 e cai no fim do ciclo. Multiplicando por ET₀, temos quanto a uva consome: **ETc = Kc × ET₀**.

### 1.4 `carregar_clima()`
Lê o CSV de Petrolina e preenche os 2 dias que faltam (08/10/2000 e 14/10/2001) pela média entre o dia anterior e o seguinte. A coluna `interpolado` marca esses dias.

### 1.5 `politica_aleatoria(rng, raw)`: o produtor simulado
Sorteia um de dois tipos de produtor:
- **Gatilho:** irriga quando a caixa passou de um certo nível de gasto (de 0,3 a 2,4 × RAW) e repõe uma parte do que faltava (30% a 110%).
- **Turno fixo:** irriga a cada N dias (1 a 7) uma lâmina proporcional ao ETc.

Os dois têm uma chance de "esquecer" de irrigar no dia (0 a 50%). Isso cria produtores bons e ruins, e é o que faz aparecerem as três classes.

### 1.6 `simular_ciclo(...)`: o coração do script
Para cada dia do ciclo:

1. Calcula `Kc` e `ETc`.
2. O produtor decide se irriga, olhando o estado da manhã.
3. Calcula o **Ks** (coeficiente de estresse): se `Dr ≤ RAW`, Ks = 1 (sem estresse). Se passou, Ks cai em linha reta até 0 quando o solo esvazia. A planta com sede fecha os estômatos e consome menos.
4. Atualiza a caixa (equação 85 do FAO-56):
   `Dr_hoje = Dr_ontem − chuva − irrigação + Ks × ETc`
5. Limita `Dr` entre 0 e TAW. Água a mais drena para baixo e se perde.
6. Rotula o dia:
   - `Dr ≤ RAW` → **0 = adequado**
   - `RAW < Dr ≤ Dr crítico` → **1 = déficit moderado**
   - `Dr > Dr crítico` → **2 = déficit crítico**

Cada linha guarda também o `TAW` do ciclo, que vira uma feature.

**Exemplo de um dia (solo de 66 mm):** ontem Dr = 20 mm. Hoje ETo = 6 mm, Kc = 0,7, então ETc = 4,2 mm. Não choveu e não irrigou. Como 20 ≤ 23,1, Ks = 1. Dr = 20 − 0 − 0 + 4,2 = **24,2 mm** → passou de 23,1, então hoje é "déficit moderado".

### 1.7 `adicionar_janelas(df)`: a memória dos últimos dias
A planta não sabe só do dia de hoje: o estado do solo é a soma do passado. Então, para cada dia, somamos ETc, chuva e irrigação dos últimos **3, 7, 14, 21 e 28 dias** e **desde a poda**, e o **saldo** (`chuva + irrigação − ETc`) de cada janela. As somas de 7 dias em diante também são divididas pelo TAW: assim "meio tanque" quer dizer a mesma coisa num solo arenoso e num argiloso. São essas somas que o firmware vai precisar guardar.

### 1.8 `main()`
Para cada ano, sorteia 48 ciclos. Cada ciclo tem a sua data de poda (qualquer dia do ano, porque no Vale não há inverno e cada produtor poda quando quer), o seu solo, a sua raiz e o seu produtor. Ciclos que passariam do fim de 2009 ficam de fora. São **467 ciclos**, cerca de 50.900 dias. Separa pelo ano da poda:
- **treino:** 2000 a 2006 (o modelo aprende aqui)
- **validação:** 2007 e 2008 (escolhemos a configuração aqui)
- **teste:** 2009 (nota final, ano que o modelo nunca viu)

Separar por ano, e não sorteando dias, evita "cola": dias vizinhos são muito parecidos, e se caíssem em grupos diferentes a nota sairia falsamente alta. Usar o ano da **poda** garante que um ciclo que vira o ano fica inteiro num grupo só.

Saída: `dados/dataset_uva.csv`.

---

## 2. `02_comparar_modelos.py`: qual algoritmo usar

### 2.1 As 39 features (entradas)
`FEATURES` é a lista do que o modelo recebe: o `TAW` do solo, dia do ciclo (`dap`), `kc`, `ETo`, `ETc`, chuva e irrigação do dia, Tmax, Tmin, UR, vento, radiação, `dias_sem_irrigar`, as somas de 3/7/14 dias e as somas de 7 a 28 dias e desde a poda divididas pelo TAW. **Note que `Dr` não está na lista**: o modelo tem que adivinhar o estado do solo só com o que o sensor e o histórico mostram.

### 2.2 Normalização
`StandardScaler` transforma cada feature em `(x − média) / desvio`. Assim, chuva em mm e UR em % ficam na mesma escala, e a rede aprende melhor. A média e o desvio são calculados **só no treino**, porque o modelo não pode "espiar" os dados de teste.

### 2.3 Os três candidatos
- **MLP** (rede neural): testa 4 tamanhos de camadas escondidas.
- **SVM com kernel RBF:** testa C = 1 e 10.
- **Random Forest:** testa 3 combinações de número de árvores e profundidade.

Cada um é treinado no treino e avaliado na validação pelo **F1 macro**, a média do F1 das três classes. Usamos F1 macro, e não acurácia, porque a acurácia pode enganar quando uma classe é bem maior que as outras.

### 2.4 As métricas no teste (2009)
- **Acurácia:** % de dias certos.
- **Revocação por classe:** dos dias que eram realmente "crítico", quantos o modelo achou. É a mais importante, porque errar um crítico é deixar a planta sofrer.
- **Matriz de confusão:** linha = verdade, coluna = resposta do modelo. A diagonal são os acertos.
- **Memória estimada:**
  - MLP: nº de pesos × 4 bytes.
  - SVM: precisa guardar milhares de "vetores de suporte" (dias de treino) inteiros.
  - RF: cada nó de cada árvore ocupa ~10 bytes.

Resultado: os três ficam entre 91% e 93% (MLP 91,0%, SVM 91,1%, RF 93,1%). A RF acerta mais dias no total, mas acha só 83% dos dias críticos e ocupa 1,9 MB; o SVM ocupa 1,2 MB. A RAM do RP2040 é de 264 KB. A MLP ocupa 7 KB e, na versão final, acha 95% dos críticos. Por isso a escolha é a MLP.

Com só 14 dias de memória, a acurácia tinha caído para cerca de 85% quando a poda passou a cair em qualquer época do ano e o solo passou a variar. O déficit do solo vem acumulando desde a poda, e 14 dias não bastavam para enxergar isso: o erro crescia ao longo do ciclo. Com as janelas de 28 dias e as somas desde a poda, voltou para cerca de 91% (DECISOES.md, seção 11).

---

## 3. `03_treinar_mlp.py`: a MLP final para a placa

### 3.1 A rede
```
39 entradas → 16 neurônios (ReLU) → 3 saídas (softmax)
```
- Cada neurônio faz `soma(peso × entrada) + bias` e passa pela **ReLU** (`max(0, x)`).
- O **softmax** transforma as 3 saídas em probabilidades que somam 1. A classe escolhida é a de maior valor.
- Total: 39×16 + 16 + 16×3 + 3 = **691 parâmetros**.

A comparação do script 02 escolheu duas camadas (32 e 16), mas a de 16 sozinha acerta praticamente o mesmo com pouco mais de um terço do tamanho, então usamos a menor.

### 3.2 O treino
- `class_weight`: erros nas classes raras (crítico é cerca de 13%) pesam mais, para o modelo não as ignorar.
- `EarlyStopping`: para quando a validação para de melhorar por 15 épocas e volta para a melhor versão. Evita decorar o treino (overfitting).

### 3.3 Exportação para MicroPython
Depois do treino, o script tira de dentro do Keras os números da rede (`get_weights()`) e escreve o arquivo `firmware/modelo/agroedge_pesos.py`. Ele contém:
- as médias e os desvios do treino, para normalizar;
- `W1` e `B1`, os pesos e bias da camada escondida;
- `W2` e `B2`, os da camada de saída.

Todos ficam guardados como `array("f", [...])`, vetores de floats de 32 bits, que ocupam 4 bytes por número (cerca de 3 KB no total).

**Por que não precisamos de TensorFlow Lite nem de INT8:** a rede é tão pequena que dá para escrever a conta dela à mão em poucas linhas de Python (próxima seção). A conta tem cerca de 670 multiplicações e roda uma vez por dia; mesmo sem FPU, isso é rápido.

### 3.4 A conferência
O script importa o `classificador.py` de verdade, roda os 3.815 dias de 2009 por ele e compara com o Keras: **as duas respostas são iguais em 100% dos dias, com 90,9% de acurácia e 95,0% dos dias críticos detectados**. Também rodei num MicroPython compilado com float de 32 bits, como o do RP2040, e o resultado foi o mesmo.

---

## 4. `firmware/modelo/`: o que vai para a BitDogLab

### 4.1 `agroedge_pesos.py` (gerado, não editar)
Só dados: `N_FEATURES`, `N_OCULTA`, `N_CLASSES`, os nomes das features (`FEATURES`, na ordem exata em que o firmware deve montar a entrada) e das classes (`CLASSES`), e os vetores `MEDIA`, `DESVIO`, `W1`, `B1`, `W2`, `B2`.

### 4.2 `classificador.py` (escrito à mão)
Tem uma função, `classificar(x)`, que faz quatro passos:
1. **Normaliza:** `z = (x − média) / desvio` para cada uma das 39 entradas.
2. **Camada escondida:** para cada um dos 16 neurônios, soma `z[i] × W1` + bias e aplica a ReLU.
3. **Camada de saída:** para cada uma das 3 classes, soma `h[j] × W2` + bias.
4. **Escolhe:** devolve o índice da maior saída (0 = adequado, 1 = moderado, 2 = crítico) e as 3 saídas.

O softmax não é calculado na placa, porque ele não muda qual saída é a maior. Isso economiza 3 exponenciais por dia.

### 4.3 `config_local.py` (editar na instalação) e `culturas.py`
O `config_local.py` é o único arquivo que muda de um local para outro:
- `CULTURA`: qual cultura está plantada, pelo nome na biblioteca `culturas.py` (hoje `uva_italia` ou `manga_tommy_atkins`).
- `DATA_REFERENCIA`: data da poda (uva) ou do início da floração (manga), para contar os dias do ciclo. Atualize a cada ciclo.
- `AGUA_DISP`: quanta água o solo segura (0,06 a 0,09 arenoso, 0,11 franco-arenoso, 0,15 a 0,18 argiloso/Vertissolo).
- `RAIZ_M` e `P_LOCAL`: em `None`, usam a raiz e o p da cultura; preencha só com medida do pomar.
- `EFICIENCIA`, `AREA_M2` e `VAZAO_L_H`: do sistema de irrigação, para a lâmina e o tempo de irrigação.

O `culturas.py` guarda os dados científicos de cada cultura (Kc ao longo do ciclo, p, raiz e a fonte de cada número). A biblioteca cresce conforme conseguimos dados de novas culturas; o resto do firmware não muda.

E três funções que o firmware usa para montar a entrada: `taw()` (1000 × água × raiz), `dap(hoje)` (dias desde a data de referência) e `kc(dap)` (Kc da cultura naquele dia).

### 4.4 `teste_classificador.py`
Roda 6 dias de 2009 (2 de cada classe, em solos de 42 a 100 mm) e mostra a classe prevista, a esperada, o tempo de cada inferência e a memória livre. Serve para confirmar na placa que tudo foi copiado certo e para medir o tempo real.

### 4.5 `historico.py`
A rede precisa das somas dos últimos 3 a 28 dias, das somas desde a poda e de quantos dias faz desde a última irrigação. O `historico.py` guarda isso num arquivo `historico.json` na flash, para não perder quando a placa reinicia, e monta as 39 entradas na ordem certa. As contas são as mesmas do `adicionar_janelas` do script 01; o script 04 confere que dão o mesmo resultado. Quando o DAP volta para trás (houve poda e a `DATA_REFERENCIA` foi atualizada), ele recomeça o ciclo.

### 4.6 `lamina.py`
A classe diz se o solo está bem; a lâmina diz quantos mm irrigar. O `lamina.py` acompanha o déficit do solo pela mesma conta do rótulo (FAO-56, eq. 84 e 85): soma o que a planta gastou (Ks × ETc) e tira a chuva e a irrigação. Se a classe for adequado, não irriga. Se for moderado ou crítico, repõe todo o déficit, dividido pela eficiência do gotejamento. O `tempo_min` converte em minutos de válvula: 1 mm em 1 m² é 1 litro.

### 4.7 Como usar no firmware (uma vez por dia, no fim do dia)
```python
import classificador, historico, lamina
import config_local as cfg

h = historico.Historico()                    # lê o historico.json
d = cfg.dap(hoje)                            # hoje = (ano, mês, dia), do RTC
x, deficit = h.fechar_dia(cfg.taw(), d, eto, chuva, irrigacao_de_hoje,
                          tmax, tmin, ur, vento, radiacao)   # do módulo de sensores e do ET0
h.salvar()
classe, saidas = classificador.classificar(x)
liquida, bruta = lamina.recomendar(classe, deficit)
minutos = lamina.tempo_min(bruta)            # válvula aberta amanhã
```

---

## 5. Como mudar algo e refazer

**Instalar em outro local:** não precisa retreinar. Edite só o `config_local.py` da placa com a cultura, o solo e a data da poda ou floração daquela área. (Outra cultura além da uva ainda pede retreino para a classe ser confiável; a ETc e a lâmina já funcionam.)

**Mudar a simulação** (por exemplo, o `P_DEPLECAO` que o Prof. Max indicar, ou uma faixa de solo diferente):
1. Ajuste o parâmetro no topo do `01_gerar_dataset.py`.
2. Rode, na pasta `modelo/`:
   ```
   python 01_gerar_dataset.py
   python 02_comparar_modelos.py
   python 03_treinar_mlp.py
   python 04_conferir_firmware.py
   ```
3. O `agroedge_pesos.py` é gerado de novo. Copie ele para a placa: o `classificador.py` e o `config_local.py` não mudam.

Dependências (só no PC, não na placa): `pip install pandas scikit-learn tabulate tensorflow`.
