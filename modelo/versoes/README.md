# Versões do classificador: comparação e decisão

> **Para a equipe:** este documento resume a discussão de 10 e 11/11/2026 sobre o classificador e lista o que
> precisamos decidir. As três versões estão guardadas lado a lado, cada uma na sua pasta. **Só uma vai para o
> firmware.** Hoje a placa usa a **v1**. A proposta do Carlos é adotar a **v3**. Leiam, comentem e decidimos juntos.

Detalhes técnicos: [`../DECISOES.md`](../DECISOES.md), seções 10, 11, 13, 14 e 15.

---

## 1. Resumo em um parágrafo

A v1 acerta 90,9%, mas só para a uva e só com dados perfeitos (irrigação sempre registrada, placa ligada desde a
poda). Nesse caso, a própria conta do balanço hídrico já acerta 100%, então a rede não tem papel. Para o produto
(qualquer cultura, dados reais de campo), criamos a v2 e a v3, treinadas com culturas sorteadas e com dados
faltando. Elas ganham da conta quando faltam dados, mas a acurácia geral fica perto de 80%, porque sem saber quanto
foi irrigado nenhum método acerta bem. **O que mais sobe a acurácia é medir a irrigação (sensor de vazão) e instalar
a placa no início do ciclo**: nessas condições, volta a ficar perto ou acima de 90%.

---

## 2. As três versões

| | **v1** (em uso) | **v2** | **v3** (proposta) |
|---|---|---|---|
| Pasta | [`v1_uva_39f/`](v1_uva_39f/) | [`v2_geral/`](v2_geral/) | [`v3_unico/`](v3_unico/) |
| Culturas no treino | só uva Itália | sintéticas + uva + manga | sintéticas + uva + manga |
| Dados de treino | perfeitos | com falhas (irrigação mal registrada, sensores com erro, solo estimado, placa ligada no meio do ciclo) | com falhas, em todas as combinações de fonte da irrigação e início do uso |
| Sabe a situação do local? | não precisa | não | **sim**: fonte da irrigação e início do uso entram como parâmetros |
| Entradas | 39 | 37 | 45 (as 37 da v2 + 8 de situação) |
| Rede | 39-16-3, 691 parâmetros, 3 KB | 37-16-3, 659 parâmetros, 2,9 KB | 45-16-3, 787 parâmetros, 3,5 KB |
| Scripts | `01` → `03` → `04` | `06` → `07` | `12` → `13` |
| Pronta para a placa? | **sim** | não (falta adaptar o `historico.py`) | não (falta adaptar o `historico.py` e o `config_local`) |
| Tag git | `modelo-v1-uva` | — | — |

---

## 3. Como chegamos aqui (o que foi debatido)

1. **A rede contra a conta (seção 10 do DECISOES).** Os rótulos de treino saem do balanço hídrico do FAO-56. Com o
   histórico completo, a placa calcula exatamente essa conta e acerta 100%; a v1 acerta 90,9%. Ou seja, com dados
   perfeitos a rede só imita a fórmula. Um avaliador pode perguntar "para que a rede?".
2. **O produto precisa servir para qualquer cultura.** Criamos a biblioteca `firmware/modelo/culturas.py` (uva e
   manga Tommy Atkins hoje; cresce com novos dados). A v1 foi treinada só com uva e não serve para a manga.
3. **Retreinar com dados faltando (v2).** Rótulo pela verdade da simulação; entradas como a placa veria no campo.
   Resultado (teste 2009): rede 70,5% × conta 64,4%. A rede ganha quando falta informação, mas o número absoluto é
   baixo porque 30% dos cenários nunca registravam a irrigação.
4. **O que sobe a acurácia (experimentos 08 a 11):**

   | Situação (rede v2, teste 2009) | Acurácia |
   |---|---|
   | Irrigação não garantida | 70,5% |
   | Produtor registra à mão (esquece um pouco e erra ±25%) | 86,5% |
   | Sensor de vazão | 90,7% |
   | Sensor de vazão + placa ligada no início do ciclo | 92,7% |

   E ligar a placa **logo depois de uma irrigação forte** elimina a perda de quem instala no meio do ciclo (balanço:
   79,7% → 83,5%, igual a ligar no início; 10 anos × 5 sementes). **Correção feita na discussão:** a perda por
   ligar no meio do ciclo é de ~5 pontos, não ~10 (o teste de 2009 tem poucos cenários e varia muito).
5. **Um modelo só para todas as situações (v3).** No produto não dá para ter uma rede por situação. A v3 é uma rede
   única que recebe a situação do local como parâmetro.

---

## 4. Resultados lado a lado

**Atenção:** os testes não são idênticos (v1 testada só com dados perfeitos; v2 e v3 com conjuntos de falhas
diferentes). Compare cada versão com a **conta do balanço no mesmo teste**.

| | Teste | Conta do balanço | Rede | Crítico detectado (rede) | Crítico chamado de adequado | Adequado chamado de crítico |
|---|---|---|---|---|---|---|
| v1 | uva, dados perfeitos | 100% | 90,9% | 95,0% | 0 de 322 (0%) | 0 de 2.440 (0%) |
| v2 | culturas variadas, dados com falhas | 64,4% | 70,5% | 87,7% | 1 de 925 (0,1%) | 323 de 2.455 (13%) |
| v3 | todas as situações de campo | 76,4% | 79,4% | 80,1% | 13 de 874 (1,5%) | 337 de 4.786 (7%) |

**v3 por fonte da irrigação** (teste 2009, 72 cenários):

| Fonte da irrigação | Conta do balanço | Rede v3 |
|---|---|---|
| Sensor de vazão | **87,6%** | 83,3% |
| Produtor informa a quantidade | 83,7% | **84,4%** |
| Produtor informa o tempo de válvula | 86,4% | **87,4%** |
| Registro de vez em quando | 74,7% | **78,5%** |
| Sem informação | 46,4% | 59,9% (só 24% dos críticos) |

Híbrido (conta com sensor de vazão, v3 nas outras fontes): **80,0%** geral.

---

## 5. Prós e contras

**v1**
- ✅ Pronta e testada no firmware; 90,9% (é o número do relatório parcial).
- ❌ Só uva; só vale com irrigação registrada e placa ligada desde a poda. Com dados perfeitos, perde para a conta.

**v2**
- ✅ Qualquer cultura; ganha da conta quando faltam dados.
- ❌ Não sabe de onde vem a irrigação: perde para a conta quando os dados estão completos. Superada pela v3.

**v3**
- ✅ Um modelo para qualquer cultura e qualquer situação; ganha da conta em 4 de 5 fontes de irrigação.
- ✅ A situação vira configuração na instalação (e no dashboard), como queremos no produto.
- ❌ Perde para a conta quando há sensor de vazão (resolvido com o híbrido).
- ❌ Detecta menos dias críticos que a conta (80% × 92%), principalmente sem informação de irrigação.
- ❌ Ainda precisa ser integrada ao firmware.

---

## 6. Proposta (Carlos): v3 com regra híbrida

1. Na instalação, configurar **cultura**, **data da poda/floração**, **fonte da irrigação** e **início do uso**.
2. **Sensor de vazão:** classe pela conta do balanço. **Quantidade, tempo de válvula ou registro parcial:** classe
   pela v3. **Sem informação de irrigação:** não mostrar classe; mostrar "registre a irrigação" + ET0/ETc.
3. Procedimento de instalação: ligar a placa no dia da poda/floração ou logo depois de uma irrigação forte.
4. Próximo hardware: sensor de vazão (dá a irrigação sem depender do produtor; com ele a BitDogLab também pode
   acionar a válvula). Depois, sensor de umidade do solo (capacitivo), que também permite rótulos reais.

---

## 7. O que precisamos decidir (checklist)

- [ ] **Qual versão vai para o firmware:** v1, v2 ou v3 (proposta: v3 com a regra híbrida da seção 6).
- [ ] **Meta de 90%:** redefinir com o Prof. Max por condição de uso (ex.: "> 90% com irrigação medida/informada
      e instalação no início do ciclo"), em vez de um número único.
- [ ] **Sem informação de irrigação:** concordamos em não mostrar a classe?
- [ ] **Sensor de vazão:** compramos e implementamos antes do campo, ou fica como próximo passo no relatório?
- [ ] **Sensor de umidade:** trocar o resistivo da bancada por um capacitivo para o campo?
- [ ] **Relatório final (17/11):** apresentar só a v1 (90,9%) ou a v1 + o estudo de robustez (v2/v3)? Proposta:
      os dois, porque o estudo justifica a rede e o sensor de vazão.
- [ ] **Com o Prof. Max:** p = 0,35 da uva, limite do crítico Ks = 0,5, faixas das culturas sintéticas, e Kc da
      manga fora da floração-maturação (pós-colheita, vegetativo, indução floral — na indução, a irrigação é
      reduzida de propósito e o sistema não deveria recomendar irrigar).

---

## 8. Depois da decisão

**Se for a v1:** nada muda no firmware. Lembrar que ela só vale para a uva.

**Se for a v3 (ou v2):**
1. Adaptar `firmware/modelo/historico.py` para montar as 45 entradas da v3 (são as mesmas contas da classe
   `PlacaGeral` do `06_gerar_dataset_geral.py`: fração do ciclo, p, somas de 3 a 28 dias e desde o início do uso
   divididas pelo TAW, e o balanço da própria placa).
2. Acrescentar no `config_local.py`: `FONTE_IRRIGACAO` (`"sensor"`, `"manual"`, `"tempo"`, `"parcial"`,
   `"nenhuma"`) e `INICIO_USO` (`"ciclo"`, `"apos_irr"`, `"meio"`).
3. Copiar `v3_unico/agroedge_pesos_v3.py` para `firmware/modelo/agroedge_pesos.py`.
4. Implementar a regra híbrida no `main.py`.
5. Escrever o equivalente do script 04 para a v3 (conferir no PC que a placa monta as mesmas entradas do treino).
6. Medir na BitDogLab o tempo de inferência e a memória.

---

## 9. Como reproduzir

Python 3 com `pip install pandas numpy scikit-learn tabulate tensorflow` (na pasta `modelo/`):

| Script | O que faz | Tempo aprox. |
|---|---|---|
| `01` → `03` → `04` | v1: dataset da uva, treino, conferência do firmware | ~2 min |
| `05_validar_eto.py` | ET0 do firmware × DataClimaBR (RMSE 0,07 mm/dia) | segundos |
| `06` → `07` | v2: dataset geral com falhas e treino | ~6 min |
| `08_experimento_vazao.py` | v2 com sensor de vazão em todos os cenários | ~2 min |
| `09_experimento_registro.py` | v2 com registro manual obrigatório | ~2 min |
| `10_experimento_inicio_apos_irrigacao.py` | placa ligada logo após irrigação forte | ~2 min |
| `11_inicio_varias_sementes.py` | confere o 09 × 10 em 10 anos e 5 sementes (só balanço) | ~5 min |
| `12` → `13` | v3: dataset com todas as situações e treino | ~3 min |

Os datasets gerados ficam em `dados/` e não vão para o git (estão no `.gitignore`); rode os scripts para recriá-los.
Todos usam semente fixa: o resultado se repete.

---

## 10. Limitações (valem para todas as versões)

- **Rótulos sintéticos:** a acurácia mede o quanto a rede reproduz o balanço do FAO-56, não o solo real. Validar
  no campo exige tensiômetro ou sensor de umidade.
- **Clima de um lugar só:** Petrolina, 2000–2009.
- **Teste pequeno:** o teste de 2009 tem de 35 a 72 cenários; diferenças de poucos pontos podem mudar com outra
  semente.
- **Manga:** só temos Kc da floração à maturação (~150 dias) e só da cv. Tommy Atkins.
