# Decisões do modelo e por quê

Registro das discussões que levaram ao modelo atual. Serve para o relatório, para o artigo e para quem entrar no projeto depois.

---

## 1. Por que MicroPython, e não C/TFLite INT8

A proposta e o roadmap falavam em C/C++ com TinyML (TensorFlow Lite Micro, rede quantizada em INT8). O firmware do projeto será em MicroPython, então trocamos.

- A rede é muito pequena (39-16-3, 691 parâmetros), e a conta dela cabe em poucas linhas de Python: normalizar, multiplicar e somar, ReLU e escolher a maior saída. Não precisa de biblioteca de inferência.
- Em float32, os pesos ocupam cerca de 3 KB em `array('f')`. A quantização INT8 economizaria memória que não nos falta.
- A classificação roda uma vez por dia, então a velocidade não é problema mesmo sem FPU.
- Conferido: o `classificador.py`, rodando num MicroPython compilado com float de 32 bits como o do RP2040, dá a mesma classe que o Keras em 100% dos dias de teste.
- **Falta:** medir o tempo de inferência na BitDogLab com o `teste_classificador.py`.

**Para o relatório:** justificar a troca com o Prof. Max, porque ela muda o que a proposta prometia ("TinyML em C" virou "MLP embarcada em MicroPython").

---

## 2. Por que há constantes no topo do `01_gerar_dataset.py`

A pergunta foi: "não deveria ser tudo calculado?".

A maior parte já é calculada: TAW, RAW, o limite do crítico, o Kc de cada dia, a ETc, o Dr diário e as janelas de 3, 7 e 14 dias. Ficam como constantes só os **dados de entrada**, que nenhuma conta tira do clima:

| Constante | Por que não é calculada |
|---|---|
| Água disponível do solo (θCC − θPMP) | Depende do tipo de solo; vem de análise de laboratório ou de tabela (FAO-56, tab. 19). |
| Profundidade da raiz | Mede-se no campo ou pega-se da literatura. |
| `P_DEPLECAO` = 0,35 | É da cultura (uva de mesa), tabelado no FAO-56 (tab. 22). |
| `KS_CRITICO` = 0,5 | É uma definição nossa de onde começa o "crítico". |
| `CICLO_DIAS` = 109 | Vem de Ávila Netto et al. (2000) para Petrolina. |
| Data da poda | Depende do calendário de cada produtor. |

O ponto fraco não é serem constantes, e sim que algumas foram **assumidas** (marcadas `ASSUMIDO` no código) e precisam ser confirmadas com o Prof. Max.

---

## 3. O que é TAW

**TAW** (*Total Available Water*, água total disponível) é quanta água o solo consegue guardar ao alcance das raízes, em mm.

- Capacidade de campo (θCC): o solo "cheio", depois que o excesso de uma chuva forte escorreu.
- Ponto de murcha (θPMP): o solo tão seco que a raiz não consegue puxar água.
- A diferença entre os dois é a água que a planta consegue usar.

`TAW = 1000 × (θCC − θPMP) × Zr`. Exemplo: `1000 × 0,11 × 0,6 = 66 mm`.

Os limites das classes saem dele:
- **RAW = 0,35 × TAW**: até gastar isso, a planta não sofre. É o limite do "adequado".
- **Dr crítico = TAW − 0,5 × (1 − 0,35) × TAW**: a partir daqui, a planta transpira menos da metade do normal. É o limite do "crítico".

O `Dr` que o balanço acompanha é quanto desse "tanque" já foi gasto: 0 é cheio, TAW é seco.

---

## 4. Petrolina e Juazeiro não têm o mesmo solo

Pela literatura geral da região (a confirmar com a Embrapa Semiárido e o Prof. Max):

- **Petrolina** (perímetros Nilo Coelho, Bebedouro): quase tudo solo arenoso ou franco-arenoso (Argissolos, Latossolos, Neossolos Quartzarênicos), com cerca de 0,06 a 0,12 m³/m³ de água disponível.
- **Juazeiro** (Maniçoba, Mandacaru): há áreas de **Vertissolo**, argiloso, que segura bem mais água.
- **Raiz da videira com gotejamento:** concentrada nos primeiros 40 a 60 cm.
- **Poda:** não há inverno, então cada produtor poda o ano inteiro, escalonando a colheita (cerca de 2,5 safras por ano). As datas fixas de 15/01 e 15/07 da primeira versão não representavam o Vale.

Conclusão: o TAW pode variar muito de uma margem do rio para a outra, então os parâmetros do solo precisam ser configuráveis.

---

## 5. Configurar só no firmware não bastava

A primeira versão aprendeu as fronteiras entre as classes para **um** solo, o de 66 mm. Ela não recebia o TAW como entrada. Num solo arenoso de 40 mm, os mesmos 7 dias sem chuva já seriam críticos, e ela não saberia. Trocar a constante só na placa não mudaria nada.

Havia dois caminhos:

1. **Um modelo por local:** a configuração fica no PC, e cada local novo exige rodar 01 → 02 → 03 e gravar novos pesos.
2. **Um modelo geral:** a simulação sorteia solos e raízes, o TAW entra como feature, e a configuração fica na placa. O mesmo arquivo de pesos serve em qualquer lugar.

---

## 6. O teste que decidiu

Geramos dois conjuntos de dados, ambos com a poda em qualquer dia do ano:
- **Solo fixo:** 66 mm.
- **Solos variados:** água disponível de 0,06 a 0,18 m³/m³ e raiz de 0,4 a 0,8 m, ou seja, TAW de 25 a 140 mm.

Resultado no teste (2009):

| Modelo | Parâmetros | Acurácia, solo 66 mm | Acurácia, solos variados | Crítico detectado, solos variados |
|---|---|---|---|---|
| Local (treinado só com 66 mm) | 435 | 85,3% | 83,9% | 83% |
| **Geral (TAW como entrada)** | 451 | 85,0% | 86,3% | 93% |
| Geral, 32 neurônios | 899 | 85,9% | 85,5% | 94% |
| Geral + janelas divididas pelo TAW | 579 | 86,0% | 86,4% | 96% |

- O modelo geral empata com o local no solo dele e ganha nos outros. O maior ganho é deixar escapar menos dias críticos.
- Redes maiores ou features extras rendem no máximo 1 ponto e dobram o tamanho, então não compensam.

**Decisão (18/10/2026): modelo geral, MLP 24-16-3, com o TAW como primeira feature.**

---

## 7. Por que a acurácia caiu de 90,7% para cerca de 85%

Não foi por causa do solo variável: o modelo local, num solo fixo, também cai para 85% quando a poda passa a ser em qualquer data.

O 90,7% da primeira versão era otimista. Todos os ciclos começavam em 15/01 ou 15/07, sempre na mesma época de chuva e de seca, e isso facilitava. Com a poda em qualquer época, o problema fica mais difícil e mais parecido com o campo.

Depois, dando à rede 28 dias de memória e as somas desde a poda, a acurácia voltou para 90,9% no mesmo cenário realista (seção 11).

**Para o artigo:** reportar o número do cenário realista com a rede final (90,9% de acurácia e 95,0% de revocação do crítico) e explicar o caminho.

---

## 8. Como ficou

- **PC** (`modelo/`): o `01_gerar_dataset.py` sorteia solo, raiz, poda e produtor para cada ciclo (467 ciclos, cerca de 50.900 dias). O `02` compara, o `03` treina e exporta os pesos e o `04` confere o caminho do firmware.
- **Placa** (`firmware/modelo/`): o `config_local.py` é o único arquivo que muda por local. Ele guarda a cultura, a data da poda ou floração e a água disponível do solo, e calcula `taw()`, `dap()` e `kc()` a partir da biblioteca `culturas.py` (seção 13). O `historico.py` monta as entradas e o `lamina.py` calcula a lâmina (seções 9 e 11).
- **Limite de uso:** o modelo foi treinado com TAW de 25 a 140 mm. Fora disso, a resposta não é confiável.

## 9. E a lâmina de irrigação?

O `classificar(x)` devolve só a **classe** do dia, não quantos mm irrigar. A lâmina pode sair do `Dr` (quanto o solo está seco): pelo FAO-56, `lâmina = Dr ÷ eficiência do gotejamento (~0,9)`. Discutimos três caminhos:

| Caminho | Como | Resultado do teste |
|---|---|---|
| Rede com 2 saídas | A MLP também prevê o Dr em mm | Erro médio de 5,0 mm (90% dos dias até 12,4 mm), com Dr médio de 21 mm. Para achar o crítico, o classificador continua melhor (89% contra 69% a 75%). |
| Balanço FAO-56 na placa | A placa guarda o histórico desde a poda e calcula o Dr exato pela fórmula | Exato, sem rede neural. |
| Só a classe | Lâmina fora do escopo por enquanto | — |

Ponto a discutir: como o rótulo vem de uma fórmula, a placa poderia calcular o Dr exato se tivesse todo o histórico desde a poda. A rede se justifica quando falta parte do histórico (na época ela usava só 14 dias; ver seções 10 e 11) ou quando entrarem sensores de umidade reais. Isso muda o que o artigo defende.

**Decisão (19/10/2026): só a classe por enquanto**, até falar com o Prof. Max.

Revendo a proposta (`AgroEdge.pdf` e roadmap), ela já separava as duas coisas: a lâmina sai do FAO-56 ("lâmina líquida diária ideal", Sprint 2), a classe sai do modelo, e o MQTT publica ET0, lâmina e estado hídrico (Sprint 4).

**Decisão (19/10/2026, revista): classe do modelo + lâmina pelo FAO-56.** A classe decide se irriga; o `lamina.py` decide quanto. Adequado não irriga; moderado ou crítico repõe todo o déficit, dividido pela eficiência (0,9, ASSUMIDO). Com a placa irrigando sozinha nos ciclos de 2009 (script 04), o solo ficou adequado em 94,6% dos dias e moderado em 5,4%, sem nenhum dia crítico. A irrigação líquida foi 71% da ETc do período e a chuva cobriu 47%; a sobra drenou.

A proposta fala em lâmina diária (ETc do dia menos a chuva). Repor o déficit acumulado dá o mesmo quando se irriga todo dia, e também serve quando a classe segura a irrigação por alguns dias.

## 10. A rede contra o próprio balanço

Ao montar o `lamina.py`, o déficit da placa ficou **igual** ao Dr do rótulo (erro 0,00 mm no script 04): com o histórico completo, a placa calcula o rótulo pela fórmula. Limiares no déficit acertam 100% do rótulo sintético, e a rede acerta 90,9%. Testamos se a rede ganha quando o histórico ou os sensores falham (dias de 2009 a partir do 14º dia de uso):

| Situação | Limiares no déficit | Rede de 14 dias | Rede de 28 dias + ciclo (atual) |
|---|---|---|---|
| Histórico completo | 100% | 82,4% | 89,6% |
| Placa ligada no DAP 30, sem histórico | 91,3% | 80,7% | 83,3% |
| Placa ligada no DAP 60, sem histórico | 84,8% | 77,4% | 73,4% |
| ET0 medida 10% acima | 83,2% | 78,5% | 80,6% |
| ET0 medida 10% abaixo | 85,1% | 82,6% | 85,5% |
| Pluviômetro mede 30% a menos | 89,3% | 77,9% | 82,3% |

O balanço ganha em quase todos os casos, porque o rótulo vem dele. Com rótulo sintético, a rede só imita a fórmula, um pouco pior. A rede atual empata com o balanço só quando a ET0 é medida abaixo do real. Ela também perde mais que a antiga quando a placa é ligada no meio do ciclo, porque as somas desde a poda começam erradas (seção 11).

Para o artigo, a rede se justifica quando o rótulo vier do campo (tensiômetros, Sprint 5): aí ela aprende o que a fórmula não captura (erro do Kc, do solo, dos sensores), e o balanço vira a linha de base a vencer. **A decidir com o Prof. Max:** manter a rede como está e reportar o balanço como linha de base, ou treinar com os dados dos tensiômetros quando existirem.

## 11. Mais memória para a rede (19/10/2026)

A meta da Sprint 3 era acurácia acima de 90%, e estávamos em 84,6%. Olhando os erros da rede de 14 dias:
- O erro crescia ao longo do ciclo: 2% nos primeiros 15 dias e 23% depois do DAP 70. O déficit vem acumulando desde a poda, e a rede só via 14 dias.
- Um terço dos erros estava a menos de 2 mm do limite entre duas classes, menos da metade de um dia de ETc.

Testamos entradas novas no teste de 2009 (as linhas com faixa ou média foram repetidas com 3 sementes):

| Entradas | Acurácia | Crítico detectado | Parâmetros |
|---|---|---|---|
| 24 de antes (janelas até 14 dias) | 84,0% | 84–88% | 451 |
| + janelas de 3 a 14 dias ÷ TAW | 84,4% | 88% | 627 |
| + somas desde a poda | 87,6% | 86% | 515 |
| + janelas de 21 e 28 dias | 89,6% | 94–96% | 579 |
| **+ janelas de 7 a 28 dias e somas desde a poda, ÷ TAW** | **90,6%** | 89–93% | 691 |
| Mesmas 24, com 32 neurônios | 85,0% | 90% | 899 |
| + balanço simples (sem Ks) | 95,6% | 93% | 483 |

- O que fez diferença foi a memória longa. Aumentar a rede quase não mudou nada.
- O balanço simples foi descartado: a rede recebe quase o próprio rótulo (seção 10).

**Decisão (19/10/2026): 39 entradas**, as 24 de antes mais ETc, chuva e saldo de 7, 14, 21 e 28 dias e desde a poda, divididos pelo TAW. A MLP final (39-16-3, 691 parâmetros, 3 KB) deu 90,9% de acurácia e 95,0% de revocação do crítico, com 100% de concordância entre Keras e `classificador.py`. A placa passa a guardar 28 dias em vez de 14, mais três somas desde a poda.

Na comparação do script 02, a Random Forest chegou a 93,1% de acurácia, mas acha só 83% dos dias críticos e ocupa 1,9 MB. A MLP continua sendo a escolha.

**Cuidado:** as somas desde a poda só estão certas se a placa estiver ligada desde a poda. Se ela for instalada ou perder o `historico.json` no meio do ciclo, a rede piora mais que a antiga (73% contra 77% quando ligada no DAP 60; seção 10). Na instalação, o ideal é ligar a placa no dia da poda.

## 12. Pendências

- Confirmar com o Prof. Max as faixas de solo e raiz, a fração p = 0,35 e o limite Ks = 0,5.
- Medir o tempo de inferência na BitDogLab.
- Validar com tensiômetros em campo (Sprint 5). Hoje a acurácia mostra que a rede aprende o balanço do FAO-56, não que acerta o campo.
- Justificar no relatório a troca de C/TFLite para MicroPython.
- Discutir com o Prof. Max a seção 10 (rede contra balanço), que muda o que o artigo defende.
- Conferir no sistema instalado a eficiência, a área e a vazão por planta do `config_local.py`.

---

## 13. Biblioteca de culturas (`firmware/modelo/culturas.py`)

A ideia do produto é o produtor informar a cultura e a fase, e o sistema se adaptar. Por isso os dados foram separados em dois tipos:

- **Dados científicos da cultura** (Kc ao longo do ciclo, fração p, profundidade de raiz): vêm da literatura e ficam no `culturas.py`, com a fonte de cada número. O produtor não tem como informá-los.
- **Dados do local** (qual cultura está plantada, data da poda ou floração, solo, irrigação): ficam no `config_local.py` e, no futuro, chegam pelo dashboard.

O resto do firmware só pergunta o Kc do dia; não sabe qual é a planta. Para incluir uma cultura nova, basta acrescentar um bloco com fonte. Sem fonte, não entra.

Culturas na biblioteca hoje:
- **Uva Itália:** Kc pela equação de Ávila Netto et al. (2000), ciclo de 109 dias após a poda, p = 0,35 (FAO-56, tab. 22).
- **Manga Tommy Atkins:** Kc por fase de Silva (2000), adotado pela Embrapa Semiárido: floração 0,44 (20 dias), queda de frutos 0,65 (39), formação 0,83 (51), maturação 0,84 (39), contando a partir da floração; p = 0,5 (Soares e Costa, 1995, via Pinto, Silva e Coelho/Embrapa; o FAO-56 não lista manga); raiz de 0,6 m. A tabela antes anotada como "Teixeira et al., 2008" é, na verdade, de Silva (2000).

Limites:
- Manga sem Kc fora do período floração–maturação (pós-colheita, fluxos vegetativos, indução, repouso) e sem dados da cv. Palmer.
- O classificador continua treinado só com uva. O próximo passo é gerar o dataset sorteando culturas (Kc, p, raiz em faixas largas) e usar entradas que valham para qualquer cultura, como já foi feito com o solo (seção 5).

