# Anemômetro Met One 014A: teste de bancada

Anemômetro de 3 conchas com chave reed (contato seco, sem alimentação). A placa conta os fechamentos por segundo (f, em Hz) e converte: **v (m/s) = 0,8 × f + 0,447**, com v = 0 quando f = 0. Faixa de 0 a 45 m/s (~56 Hz).

## Materiais
- [ ] BitDogLab com MicroPython v1.29 e cabo USB
- [ ] Anemômetro Met One 014A com o cabo
- [ ] Multímetro (modo continuidade/bipe ou ohms)
- [ ] Resistor de 10 kΩ (pull-up)
- [ ] Resistor de 1 kΩ e capacitor de 100 nF (filtro RC)
- [ ] Jumpers macho-fêmea e protoboard pequena
- [ ] Ventilador (para a checagem final)

Para o primeiro teste só os jumpers e o multímetro bastam. Os componentes entram na ligação definitiva.

## Arquivos para copiar para a placa
`anemometro.py`, `config_local.py` (a versão nova, com `PINO_ANEMOMETRO`) e `teste_anemometro.py`.
No MicroPico: botão direito em cada arquivo, *Upload file to Pico*. Pelo terminal: `mpremote cp anemometro.py config_local.py teste_anemometro.py :`.

## 1. Achar o par de fios (multímetro)
No cabo Campbell original o **preto** é o sinal. Se o cabo não for original:
1. Multímetro em continuidade. Ponta em dois fios de cada vez.
2. Gire as conchas devagar com a mão. O par certo **bipa e para de bipar** conforme gira (a reed abre e fecha). Os outros pares ficam sempre mudos (ou sempre bipando, se forem blindagem/terra do mesmo ponto).
3. Conte quantos bipes dá **uma volta completa**. Anote: confere com o MODO 1.

Na reed tanto faz qual fio do par vai no GPIO e qual vai no GND.

## 2. Ligação
Pino **GPIO18** (conector IDC, fileira "GP18 GP19 GP20 GP4 GP9 GP8 5V": o GP18 é o 1º, contando da esquerda; confira a serigrafia). O GND e o 3V3 ficam na outra fileira ("GND GP16 GP17 GND GP28 3V3 GND": GND no 1º ou 4º pino, 3V3 no 6º). O GP17 é do AM2302 e o GP16 do pluviômetro.

Teste rápido, sem componentes: um fio do par no GPIO18 e o outro no GND. O pull-up interno segura o pino em 1.

Ligação definitiva:
```
3V3 ──[10 kΩ]──┐
fio do sensor ─┴──[1 kΩ]──┬── GPIO18
                       [100 nF]
outro fio ──── GND ───────┘
```
O 10 kΩ é um pull-up mais forte que o interno (~50 kΩ) e o filtro 1 kΩ/100 nF corta picos de ruído do cabo longo. O capacitor vai do GPIO18 ao GND.

## 3. Rodar o teste
Abra `teste_anemometro.py`, escolha `MODO = 1`, `2` ou `3` no topo e rode (Run no MicroPico/Thonny). O **botão A** passa para o próximo modo sem reiniciar. Ctrl+C para parar.

| Modo | O que fazer | Resultado esperado |
|---|---|---|
| 1, contato | Girar a concha **bem devagar** com a mão | Pino em 1 (aberto); a cada fechamento vai a 0 e a contagem sobe **1**. "Fechamentos" e "pulsos na interrupção" iguais. O número por volta bate com o que o multímetro mostrou |
| 2, medição | Parado, depois girar com a mão, depois ventilador | Parado: **0,00 m/s** (nunca 0,447). Com a mão: poucos m/s (~1 a 4). Ventilador doméstico a ~1 m: ~2 a 6 m/s, estável de um segundo para o outro. Nenhum aviso de rejeitados (ou poucos) |
| 3, debounce | Ventilador na velocidade máxima ou sopro forte | "Menor entre pulsos aceitos" perto de 1/f. Repique abaixo de 2 ms sendo rejeitado é normal na reed |

Diagnóstico:
- **"nenhum pulso em 10 s"**: par de fios errado, fio fora do GPIO18/GND, ou conchas paradas.
- **Pino em 0 o tempo todo**: a reed parou fechada (gire um pouco) ou o fio do GPIO está em curto com o GND.
- **Muitos rejeitados ou f acima de 60 Hz**: ruído. Use o 10 kΩ e o filtro RC, e afaste o cabo de fios de força.
- **Contagem dobrando** (2 por fechamento no MODO 1): repique maior que 2 ms. Suba `ANEMO_DEBOUNCE_MS` no `config_local.py` (até ~10 ms ainda não perde pulso a 45 m/s).

## 4. Configuração (`config_local.py`)
- `PINO_ANEMOMETRO = 18`
- `ANEMO_M = 0.8`, `ANEMO_B = 0.447`: calibração de fábrica do 014A.
- `ANEMO_ALTURA_M = 2.0` (ASSUMIDO): altura das conchas. Se for instalado em outra altura, o `anemometro.py` converte para 2 m (FAO-56, eq. 47), que é o que o ET0 e o modelo usam.
- `ANEMO_DEBOUNCE_MS = 2` (ASSUMIDO): conferir no MODO 3.

## 5. No firmware final
O `vento` que o modelo recebe é a **média diária a 2 m, em m/s** (mesma unidade do `Velocidade_Vento` do DataClimaBR). Ainda não há `main.py` nem cálculo de ET0 no firmware; quando houver, o laço fica assim, junto do pluviômetro:

```python
import anemometro, pluviometro
a = anemometro.Anemometro()          # carrega vento_hoje.json, se existir
p = pluviometro.Pluviometro()
# no laço principal, a cada 1 s (ou a cada N s; a média é ponderada pelo tempo):
n, f, v = a.medir()
a.adicionar(v, a.ultimo_dt)
# a cada ~10 min: a.salvar(); p.salvar()
# no fim do dia:
u2, rajada, amostras = a.fechar_dia()   # u2 entra no Penman-Monteith e em historico.fechar_dia(vento=u2)
chuva = p.fechar_dia()
```
